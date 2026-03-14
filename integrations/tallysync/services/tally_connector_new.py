import re
import requests
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List, Any
from django.conf import settings
from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape as xml_escape
import logging

logger = logging.getLogger(__name__)


class TallyConnectionError(Exception):
    """Raised when communication with the Tally server fails."""
    pass


# Regex to strip invalid XML characters (control chars except tab, newline, carriage return)
_INVALID_XML_CHARS_RE = re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]')
# Regex to strip invalid numeric XML character references (&#0; through &#31; except &#9; &#10; &#13;)
_INVALID_XML_REFS_RE = re.compile(r'&#([0-9]+);')


class TallyConnector:
    """Handles communication with Tally ODBC server

    SECURITY: All user inputs in XML requests must be escaped using
    _escape_xml() to prevent XML injection attacks.
    """

    def __init__(self, host: str = None, port: int = None):
        from integrations.tallysync.models import TallySyncSettings
        db_settings = TallySyncSettings.load()

        # If tunnel_url is set, use it (overrides host:port for production)
        self.tunnel_url = db_settings.tunnel_url.strip() if db_settings.tunnel_url else ''
        if self.tunnel_url:
            self.host = self.tunnel_url
            self.port = 443  # tunnel is HTTPS
            self.base_url = self.tunnel_url.rstrip('/')
            self.use_tunnel = True
        else:
            if not host or not port:
                host = host or db_settings.server_ip or 'localhost'
                port = port or int(db_settings.server_port or 2245)
            self.host = host
            self.port = port
            self.base_url = f"http://{self.host}:{self.port}"
            self.use_tunnel = False
        self.timeout = getattr(settings, 'TALLY_TIMEOUT', 30)

    @staticmethod
    def _escape_xml(value: str) -> str:
        """Escape XML special characters to prevent injection

        SECURITY FIX: Escapes &, <, >, ', " to prevent XML injection.
        Always use this method before inserting user input into XML.
        """
        if not value:
            return ''
        return xml_escape(value, entities={
            "'": "&apos;",
            "\"": "&quot;"
        })
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test Tally server connection with detailed diagnostics.

        Returns:
            dict: {
                'success': bool,
                'status': str,  # 'connected', 'timeout', 'refused', 'unreachable', 'invalid_response', 'unknown_error'
                'message': str,  # Human-readable message
                'details': dict,  # Technical details for debugging
            }
        """
        result = {
            'success': False,
            'status': 'unknown_error',
            'message': 'Connection test not completed',
            'details': {}
        }

        try:
            logger.info(f"Testing Tally connection to {self.base_url}")
            headers = {}
            if self.use_tunnel:
                headers['ngrok-skip-browser-warning'] = '1'
            response = requests.get(
                self.base_url,
                headers=headers,
                timeout=self.timeout
            )

            # Check response
            if 'TallyPrime Server is Running' in response.text or 'Tally' in response.text:
                result['success'] = True
                result['status'] = 'connected'
                result['message'] = f'✅ Successfully connected to Tally server at {self.host}:{self.port}'
                result['details'] = {
                    'status_code': response.status_code,
                    'response_time_ms': response.elapsed.total_seconds() * 1000,
                    'server_type': 'TallyPrime' if 'TallyPrime' in response.text else 'Tally ERP',
                }
                logger.info(f"Connection successful: {result['message']}")
            else:
                result['status'] = 'invalid_response'
                result['message'] = f'⚠️ Connected but invalid response (not a Tally server?)'
                result['details'] = {
                    'status_code': response.status_code,
                    'response_preview': response.text[:200],
                }
                logger.warning(f"Invalid response from {self.base_url}: {response.text[:100]}")

        except requests.exceptions.Timeout:
            result['status'] = 'timeout'
            result['message'] = f'❌ Connection timeout after {self.timeout}s. Check: (1) Is Tally running? (2) Is port {self.port} correct? (3) Is firewall open?'
            result['details'] = {
                'host': self.host,
                'port': self.port,
                'timeout_seconds': self.timeout,
            }
            logger.error(f"Connection timeout to {self.base_url}")

        except requests.exceptions.ConnectionError as e:
            if 'Connection refused' in str(e):
                result['status'] = 'refused'
                result['message'] = f'❌ Connection refused. Tally HTTP service may be disabled. Check: (1) F1 → Settings → Connectivity in Tally (2) Is port {self.port} listening?'
            else:
                result['status'] = 'unreachable'
                result['message'] = f'❌ Cannot reach {self.host}:{self.port}. Check: (1) Is IP correct? (2) Is port forwarding configured? (3) Network connectivity?'
            result['details'] = {
                'host': self.host,
                'port': self.port,
                'error': str(e),
            }
            logger.error(f"Connection error to {self.base_url}: {e}")

        except Exception as e:
            result['status'] = 'unknown_error'
            result['message'] = f'❌ Unexpected error: {str(e)}'
            result['details'] = {
                'error_type': type(e).__name__,
                'error_message': str(e),
            }
            logger.exception(f"Unexpected error testing connection to {self.base_url}")

        return result
    
    @staticmethod
    def _sanitize_xml(xml_text: str) -> str:
        """Remove invalid XML characters that cause parsing failures.

        Tally responses sometimes contain control characters (e.g. in ledger
        names or narrations) that are illegal in XML.  This strips them before
        we hand the text to the parser.

        Also strips TallyUDF namespace declarations and UDF: tag prefixes
        that cause 'unbound prefix' XML parse errors in Collection responses.
        """
        # Strip raw control characters
        xml_text = _INVALID_XML_CHARS_RE.sub('', xml_text)
        # Strip numeric character references to invalid codepoints
        xml_text = _INVALID_XML_REFS_RE.sub(
            lambda m: '' if int(m.group(1)) < 32 and int(m.group(1)) not in (9, 10, 13) else m.group(0),
            xml_text,
        )
        # Strip TallyUDF namespace (Collection responses include xmlns:UDF="TallyUDF")
        xml_text = xml_text.replace('xmlns:UDF="TallyUDF"', '')
        xml_text = re.sub(r'<UDF:', '<', xml_text)
        xml_text = re.sub(r'</UDF:', '</', xml_text)
        return xml_text

    def send_request(self, xml_request: str, timeout: int = None) -> str:
        """Send XML request to Tally and return sanitized response.

        Retries once on ConnectionResetError (Tally cloud servers drop connections
        intermittently between batches). Fresh session per attempt avoids reusing
        a closed TCP connection.

        Raises TallyConnectionError on failure so callers can distinguish
        'no data' from 'connection failed'.
        """
        import time
        t = timeout or self.timeout
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                # Fresh session each attempt — avoids reusing a reset connection
                with requests.Session() as session:
                    req_headers = {'Content-Type': 'application/xml', 'Connection': 'close'}
                    if self.use_tunnel:
                        req_headers['ngrok-skip-browser-warning'] = '1'
                    response = session.post(
                        self.base_url,
                        data=xml_request,
                        headers=req_headers,
                        timeout=t,
                    )
                response.raise_for_status()
                return self._sanitize_xml(response.text)
            except requests.exceptions.Timeout:
                msg = f"Request timed out after {t[1] if isinstance(t, tuple) else t} seconds"
                logger.error(msg)
                raise TallyConnectionError(msg)
            except requests.exceptions.ConnectionError as e:
                if attempt < max_attempts:
                    wait = attempt * 3  # 3s, 6s
                    logger.warning(f"Connection error (attempt {attempt}/{max_attempts}), retrying in {wait}s: {e}")
                    time.sleep(wait)
                    continue
                msg = f"Request failed: {e}"
                logger.error(msg, exc_info=True)
                raise TallyConnectionError(msg)
            except requests.exceptions.RequestException as e:
                msg = f"Request failed: {e}"
                logger.error(msg, exc_info=True)
                raise TallyConnectionError(msg)
    
    def fetch_companies(self) -> List[Dict]:
        """Fetch list of all companies"""
        xml_request = """<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
<HEADER>
<VERSION>1</VERSION>
<TALLYREQUEST>Export</TALLYREQUEST>
<TYPE>Collection</TYPE>
<ID>Companies</ID>
</HEADER>
<BODY>
<DESC>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
</STATICVARIABLES>
<TDL>
<TDLMESSAGE>
<COLLECTION NAME="Companies">
<TYPE>Company</TYPE>
</COLLECTION>
</TDLMESSAGE>
</TDL>
</DESC>
</BODY>
</ENVELOPE>"""
        
        response = self.send_request(xml_request)
        return self._parse_companies(response)

    def fetch_cost_centres(self, company_name: str) -> List[Dict]:
        """Fetch cost centres for a company"""
        # SECURITY FIX: Properly escape XML to prevent injection
        company_name_escaped = self._escape_xml(company_name)
        
        xml_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
<HEADER>
<VERSION>1</VERSION>
<TALLYREQUEST>Export</TALLYREQUEST>
<TYPE>Collection</TYPE>
<ID>CostCentres</ID>
</HEADER>
<BODY>
<DESC>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company_name_escaped}</SVCURRENTCOMPANY>
</STATICVARIABLES>
</DESC>
</BODY>
</ENVELOPE>"""
        
        response = self.send_request(xml_request)
        return self._parse_cost_centres(response)

    def fetch_ledgers(self, company_name: str) -> List[Dict]:
        """Fetch ledgers for a company"""
        # SECURITY FIX: Properly escape XML to prevent injection
        company_name_escaped = self._escape_xml(company_name)
        
        xml_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
<HEADER>
<VERSION>1</VERSION>
<TALLYREQUEST>Export</TALLYREQUEST>
<TYPE>Collection</TYPE>
<ID>Ledgers</ID>
</HEADER>
<BODY>
<DESC>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company_name_escaped}</SVCURRENTCOMPANY>
</STATICVARIABLES>
<TDL>
<TDLMESSAGE>
<COLLECTION NAME="Ledgers">
<TYPE>Ledger</TYPE>
<FETCH>Name, Parent, GUID</FETCH>
</COLLECTION>
</TDLMESSAGE>
</TDL>
</DESC>
</BODY>
</ENVELOPE>"""
        
        response = self.send_request(xml_request)
        return self._parse_ledgers(response)

    def fetch_groups(self, company_name: str) -> List[Dict]:
        """Fetch groups for a company"""
        # SECURITY FIX: Properly escape XML to prevent injection
        company_name_escaped = self._escape_xml(company_name)
        
        xml_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
<HEADER>
<VERSION>1</VERSION>
<TALLYREQUEST>Export</TALLYREQUEST>
<TYPE>Collection</TYPE>
<ID>Groups</ID>
</HEADER>
<BODY>
<DESC>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company_name_escaped}</SVCURRENTCOMPANY>
</STATICVARIABLES>
</DESC>
</BODY>
</ENVELOPE>"""
        
        response = self.send_request(xml_request)
        return self._parse_groups(response)

    def fetch_vouchers(self, company_name: str, from_date: str, to_date: str) -> List[Dict]:
        """Fetch vouchers for a date range using TDL Collection.

        Uses Collection-based export instead of DayBook report to bypass
        Tally's current period restriction (Alt+F2). The DayBook report
        only returns vouchers within the GUI-selected period, while a
        TDL Collection of type Voucher returns all data regardless.

        Dates in format: YYYYMMDD (e.g., 20251101)
        """
        # SECURITY FIX: Properly escape XML to prevent injection
        company_name_escaped = self._escape_xml(company_name)
        from_date_escaped = self._escape_xml(from_date)
        to_date_escaped = self._escape_xml(to_date)

        xml_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
<HEADER>
<VERSION>1</VERSION>
<TALLYREQUEST>Export</TALLYREQUEST>
<TYPE>Collection</TYPE>
<ID>VchExport</ID>
</HEADER>
<BODY>
<DESC>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company_name_escaped}</SVCURRENTCOMPANY>
</STATICVARIABLES>
<TDL>
<TDLMESSAGE>
<COLLECTION NAME="VchExport">
<TYPE>Voucher</TYPE>
<FILTER>DateRangeFilter</FILTER>
<FETCH>DATE, GUID, VOUCHERTYPENAME, VOUCHERNUMBER, PARTYLEDGERNAME, NARRATION, REFERENCE, ISINVOICE, ISCANCELLED, AMOUNT, COSTCENTRENAME</FETCH>
<FETCH>MASTERID, TMS_VCHNARRBILLMONTH, TMS_VCHNARRBILLMONT</FETCH>
<FETCH>BASICSHIPNAME, PARTYGSTIN, BASICBUYERNAME, BASICBUYERGSTIN, BASICBUYERSTATE, STATENAME</FETCH>
<FETCH>BASICBUYERADDR.LIST, BASICSHIPADDR.LIST, CONSIGNEENAME, CONSIGNEEGSTIN</FETCH>
<FETCH>EWAYBILLNUMBER, PAYMENTMODE, PAYMENTFAVOURING, CHEQUENUMBER, CHEQUEDATE, BILLCREDITPERIOD</FETCH>
<FETCH>LEDGERENTRIES.LIST, ALLLEDGERENTRIES.LIST, ALLINVENTORYENTRIES.LIST, BILLALLOCATIONS.LIST</FETCH>
</COLLECTION>
<SYSTEM TYPE="Formulae" NAME="DateRangeFilter">$Date &gt;= $$Date:"{from_date_escaped}" AND $Date &lt;= $$Date:"{to_date_escaped}"</SYSTEM>
</TDLMESSAGE>
</TDL>
</DESC>
</BODY>
</ENVELOPE>"""

        # Voucher fetches can be slow on cloud Tally servers — use 5 min read timeout
        # Tuple: (connect_timeout, read_timeout) — connect must succeed in 10s
        response = self.send_request(xml_request, timeout=(10, 300))
        return self._parse_vouchers(response)

    def fetch_voucher_count(self, company_name: str, from_date: str, to_date: str) -> int:
        """Fetch count of vouchers for a date range from Tally (lightweight, no ledger entries)."""
        company_name_escaped = self._escape_xml(company_name)
        from_date_escaped = self._escape_xml(from_date)
        to_date_escaped = self._escape_xml(to_date)

        xml_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
<HEADER>
<VERSION>1</VERSION>
<TALLYREQUEST>Export</TALLYREQUEST>
<TYPE>Collection</TYPE>
<ID>VchCount</ID>
</HEADER>
<BODY>
<DESC>
<STATICVARIABLES>
<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
<SVCURRENTCOMPANY>{company_name_escaped}</SVCURRENTCOMPANY>
</STATICVARIABLES>
<TDL>
<TDLMESSAGE>
<COLLECTION NAME="VchCount">
<TYPE>Voucher</TYPE>
<FILTER>DateRangeFilter</FILTER>
<FETCH>DATE</FETCH>
</COLLECTION>
<SYSTEM TYPE="Formulae" NAME="DateRangeFilter">$Date &gt;= $$Date:"{from_date_escaped}" AND $Date &lt;= $$Date:"{to_date_escaped}"</SYSTEM>
</TDLMESSAGE>
</TDL>
</DESC>
</BODY>
</ENVELOPE>"""

        response = self.send_request(xml_request)
        try:
            root = ET.fromstring(response)
            return len(root.findall('.//VOUCHER'))
        except ET.ParseError:
            return -1

    # Parsing methods
    
    def _parse_companies(self, xml_response: str) -> List[Dict]:
        """Parse companies from XML response"""
        companies = []
        try:
            root = ET.fromstring(xml_response)
            for company in root.findall('.//COMPANY'):
                name = company.get('NAME', '')
                if name:
                    companies.append({'name': name})
        except ET.ParseError as e:
            logger.warning(f"XML parsing error: {e}", exc_info=True)
        
        return companies
    
    def _parse_cost_centres(self, xml_response: str) -> List[Dict]:
        """Parse cost centres from XML response"""
        cost_centres = []
        try:
            root = ET.fromstring(xml_response)
            
            # Correct path: ENVELOPE -> BODY -> DATA -> COLLECTION -> COSTCENTRE
            collection = root.find('.//COLLECTION')
            
            if collection is not None:
                for cc in collection.findall('COSTCENTRE'):
                    name = cc.get('NAME', '')
                    if name and name.strip():
                        cost_centres.append({'name': name})
            
        except ET.ParseError as e:
            logger.warning(f"XML parsing error: {e}", exc_info=True)
        
        return cost_centres
    
    def _parse_groups(self, xml_response: str) -> List[Dict]:
        """Parse groups from XML response"""
        groups = []
        try:
            root = ET.fromstring(xml_response)
            collection = root.find('.//COLLECTION')
            
            if collection is not None:
                for group in collection.findall('GROUP'):
                    name = group.get('NAME', '')
                    if name:
                        groups.append({'name': name})
        except ET.ParseError as e:
            logger.warning(f"XML parsing error: {e}", exc_info=True)
        
        return groups

    def _parse_ledgers(self, xml_response: str) -> List[Dict]:
        """Parse ledgers from XML response"""
        ledgers = []
        try:
            root = ET.fromstring(xml_response)
            collection = root.find('.//COLLECTION')
            
            if collection is not None:
                for ledger in collection.findall('LEDGER'):
                    name = ledger.get('NAME', '')
                    parent_elem = ledger.find('PARENT')
                    parent = parent_elem.text if parent_elem is not None else ''
                    guid_elem = ledger.find('GUID')
                    guid = guid_elem.text if guid_elem is not None else ''
                    
                    if name:
                        ledgers.append({
                            'name': name,
                            'parent': parent,
                            'guid': guid
                        })
        except ET.ParseError as e:
            logger.warning(f"XML parsing error: {e}", exc_info=True)
        
        return ledgers
    
    def _parse_vouchers(self, xml_response: str) -> List[Dict]:
        """Parse vouchers from XML response with full details"""
        vouchers = []
        try:
            root = ET.fromstring(xml_response)
            for voucher in root.findall('.//VOUCHER'):
                guid_elem = voucher.find('GUID')
                
                if guid_elem is not None:
                    # UDF fields — billing month (two possible tag names, Tally uses either)
                    # NOTE: must use `is not None` not `or` — ET elements are falsy when childless
                    billing_month_el = voucher.find('.//TMS_VCHNARRBILLMONTH')
                    if billing_month_el is None:
                        billing_month_el = voucher.find('.//TMS_VCHNARRBILLMONT')
                    billing_month = billing_month_el.text.strip() if billing_month_el is not None and billing_month_el.text else ''

                    # need_to_pay = PAYMENTFAVOURING (who payment is made to/received from)
                    need_to_pay = self._get_element_text(voucher, 'PAYMENTFAVOURING')

                    # remark = NARRATION (Tally's free-text remark field)
                    remark = self._get_element_text(voucher, 'NARRATION')

                    payment_mode = self._get_element_text(voucher, 'PAYMENTMODE')
                    # BILLCREDITPERIOD stores the human-readable period in attribute P (e.g. "7 Days"), not text
                    credit_period_el = voucher.find('.//BILLCREDITPERIOD')
                    credit_period = credit_period_el.get('P', '').strip() if credit_period_el is not None else ''

                    master_id_text = self._get_element_text(voucher, 'MASTERID')
                    master_id = int(master_id_text) if master_id_text.isdigit() else None

                    # Party/buyer/consignee details
                    party_name = self._get_element_text(voucher, 'BASICSHIPNAME')
                    party_gstin = self._get_element_text(voucher, 'PARTYGSTIN')
                    party_state = self._get_element_text(voucher, 'STATENAME')
                    buyer_name = self._get_element_text(voucher, 'BASICBUYERNAME')
                    buyer_gstin = self._get_element_text(voucher, 'BASICBUYERGSTIN')
                    buyer_state = self._get_element_text(voucher, 'BASICBUYERSTATE')
                    consignee_name = self._get_element_text(voucher, 'CONSIGNEENAME')
                    consignee_gstin = self._get_element_text(voucher, 'CONSIGNEEGSTIN')

                    # E-way bill and cheque
                    eway_bill_number = self._get_element_text(voucher, 'EWAYBILLNUMBER')
                    cheque_number = self._get_element_text(voucher, 'CHEQUENUMBER')
                    cheque_date_str = self._get_element_text(voucher, 'CHEQUEDATE')

                    voucher_data = {
                        'date': self._get_element_text(voucher, 'DATE'),
                        'voucher_type': self._get_element_text(voucher, 'VOUCHERTYPENAME'),
                        'voucher_number': self._get_element_text(voucher, 'VOUCHERNUMBER'),
                        'guid': self._get_element_text(voucher, 'GUID'),
                        'party_ledger_name': self._get_element_text(voucher, 'PARTYLEDGERNAME'),
                        'party_name': party_name,
                        'party_gstin': party_gstin,
                        'party_state': party_state,
                        'buyer_name': buyer_name,
                        'buyer_gstin': buyer_gstin,
                        'buyer_state': buyer_state,
                        'consignee_name': consignee_name,
                        'consignee_gstin': consignee_gstin,
                        'cost_centre_name': self._get_element_text(voucher, 'COSTCENTRENAME'),
                        'narration': self._get_element_text(voucher, 'NARRATION'),
                        'reference': self._get_element_text(voucher, 'REFERENCE'),
                        'is_invoice': self._get_element_text(voucher, 'ISINVOICE') == 'Yes',
                        'is_cancelled': self._get_element_text(voucher, 'ISCANCELLED') == 'Yes',
                        'billing_month': billing_month,
                        'need_to_pay': need_to_pay,
                        'remark': remark,
                        'payment_mode': payment_mode,
                        'credit_period': credit_period,
                        'eway_bill_number': eway_bill_number,
                        'cheque_number': cheque_number,
                        'cheque_date': cheque_date_str,
                        'master_id': master_id,
                        'transaction_type': '',   # from party ledger entry TRANSACTIONTYPE
                        'utr_number': '',         # from party ledger entry UNIQUEREFERENCENUMBER
                        'amount': 0.0,  # Will calculate from ledgers
                        'raw_xml': ET.tostring(voucher, encoding='unicode'),
                        'ledger_entries': [],
                        'cost_allocations': [],
                        'bill_references': [],
                    }
                    
                    # Parse ledger entries and find amount
                    # DayBook uses LEDGERENTRIES.LIST, Collection uses ALLLEDGERENTRIES.LIST
                    party_amount = 0.0
                    ledger_entries_els = voucher.findall('.//ALLLEDGERENTRIES.LIST')
                    if not ledger_entries_els:
                        ledger_entries_els = voucher.findall('.//LEDGERENTRIES.LIST')
                    for entry in ledger_entries_els:
                        ledger_name = self._get_element_text(entry, 'LEDGERNAME')
                        # SECURITY FIX: Use Decimal for all financial amounts
                        amount = self._get_element_decimal(entry, 'AMOUNT', '0')
                        is_party = self._get_element_text(entry, 'ISPARTYLEDGER') == 'Yes'
                        is_debit = self._get_element_text(entry, 'ISDEEMEDPOSITIVE') == 'Yes'

                        # Extract GST details from ledger entry
                        gst_class = self._get_element_text(entry, 'GSTCLASS')
                        gst_hsn_code = self._get_element_text(entry, 'HSNCODE')

                        # GST rates - use Decimal for precision
                        cgst_rate = self._get_element_decimal(entry, 'CGSTRATE', '0')
                        sgst_rate = self._get_element_decimal(entry, 'SGSTRATE', '0')
                        igst_rate = self._get_element_decimal(entry, 'IGSTRATE', '0')
                        cess_rate = self._get_element_decimal(entry, 'CESSRATE', '0')

                        # Calculate GST amounts
                        cgst_amount = Decimal('0')
                        sgst_amount = Decimal('0')
                        igst_amount = Decimal('0')
                        cess_amount = Decimal('0')

                        # If this is a GST ledger itself, the amount IS the GST
                        if 'cgst' in ledger_name.lower():
                            cgst_amount = abs(amount)
                        elif 'sgst' in ledger_name.lower():
                            sgst_amount = abs(amount)
                        elif 'igst' in ledger_name.lower():
                            igst_amount = abs(amount)
                        elif 'cess' in ledger_name.lower():
                            cess_amount = abs(amount)
                        else:
                            # For non-GST ledgers, calculate from rates
                            base_amount = abs(amount)
                            if cgst_rate > 0:
                                cgst_amount = base_amount * cgst_rate / 100
                            if sgst_rate > 0:
                                sgst_amount = base_amount * sgst_rate / 100
                            if igst_rate > 0:
                                igst_amount = base_amount * igst_rate / 100
                            if cess_rate > 0:
                                cess_amount = base_amount * cess_rate / 100

                        # Extract TDS details - use Decimal
                        tds_nature = self._get_element_text(entry, 'NATUREOFREMITTANCE')
                        tds_section = self._get_element_text(entry, 'TDSSECTION')
                        tds_amount = abs(self._get_element_decimal(entry, 'TDSAMOUNT', '0'))

                        # Store ledger entry with GST and TDS details
                        # Keep as Decimal - sync_service.py expects Decimal
                        ledger_entry = {
                            'ledger_name': ledger_name,
                            'amount': amount,
                            'is_debit': is_debit,
                            'is_party_ledger': is_party,
                            'gst_class': gst_class,
                            'gst_hsn_code': gst_hsn_code,
                            'cgst_rate': cgst_rate,
                            'sgst_rate': sgst_rate,
                            'igst_rate': igst_rate,
                            'cess_rate': cess_rate,
                            'cgst_amount': cgst_amount,
                            'sgst_amount': sgst_amount,
                            'igst_amount': igst_amount,
                            'cess_amount': cess_amount,
                            'tds_nature_of_payment': tds_nature,
                            'tds_section': tds_section,
                            'tds_amount': tds_amount
                        }
                        voucher_data['ledger_entries'].append(ledger_entry)
                        
                        # If this is the party ledger, use its amount and extract payment details
                        if is_party:
                            party_amount = abs(amount)
                            # TRANSACTIONTYPE and UNIQUEREFERENCENUMBER live inside ledger entries
                            if not voucher_data['transaction_type']:
                                voucher_data['transaction_type'] = self._get_element_text(entry, 'TRANSACTIONTYPE')
                            if not voucher_data['utr_number']:
                                voucher_data['utr_number'] = self._get_element_text(entry, 'UNIQUEREFERENCENUMBER')
                        
                        # Parse cost centre allocations within ledger entries
                        # Look in ACCOUNTINGALLOCATIONS (not inventory level)
                        for acct_alloc in entry.findall('.//ACCOUNTINGALLOCATIONS.LIST'):
                            for cat_alloc in acct_alloc.findall('.//CATEGORYALLOCATIONS.LIST'):
                                for cc_alloc in cat_alloc.findall('.//COSTCENTREALLOCATIONS.LIST'):
                                    cc_name = self._get_element_text(cc_alloc, 'NAME')
                                    # SECURITY FIX: Use Decimal for cost centre amounts
                                    cc_amount = abs(self._get_element_decimal(cc_alloc, 'AMOUNT', '0'))

                                    if cc_name and cc_amount > 0:
                                        voucher_data['cost_allocations'].append({
                                            'ledger_name': ledger_name,
                                            'cost_centre_name': cc_name,
                                            'amount': cc_amount
                                        })

                    # Also check inventory level cost centres (for Sales invoices)
                    for inv_entry in voucher.findall('.//ALLINVENTORYENTRIES.LIST'):
                        inv_ledger = self._get_element_text(inv_entry, 'STOCKITEMNAME')
                        for acct_alloc in inv_entry.findall('.//ACCOUNTINGALLOCATIONS.LIST'):
                            for cat_alloc in acct_alloc.findall('.//CATEGORYALLOCATIONS.LIST'):
                                for cc_alloc in cat_alloc.findall('.//COSTCENTREALLOCATIONS.LIST'):
                                    cc_name = self._get_element_text(cc_alloc, 'NAME')
                                    # SECURITY FIX: Use Decimal for cost centre amounts
                                    cc_amount = abs(self._get_element_decimal(cc_alloc, 'AMOUNT', '0'))

                                    if cc_name and cc_amount > 0:
                                        voucher_data['cost_allocations'].append({
                                            'ledger_name': inv_ledger or 'Inventory',
                                            'cost_centre_name': cc_name,
                                            'amount': cc_amount
                                        })
                    
                    # Parse bill references from BILLALLOCATIONS.LIST within ledger entries
                    for entry in voucher.findall('.//ALLLEDGERENTRIES.LIST') or voucher.findall('.//LEDGERENTRIES.LIST'):
                        entry_ledger = self._get_element_text(entry, 'LEDGERNAME')
                        for bill_alloc in entry.findall('.//BILLALLOCATIONS.LIST'):
                            bill_name = self._get_element_text(bill_alloc, 'NAME')
                            bill_type = self._get_element_text(bill_alloc, 'BILLTYPE')
                            bill_amount = self._get_element_decimal(bill_alloc, 'AMOUNT', '0')
                            if bill_name:
                                voucher_data['bill_references'].append({
                                    'ledger_name': entry_ledger,
                                    'bill_name': bill_name,
                                    'bill_type': bill_type,
                                    'amount': abs(bill_amount),
                                })

                    # Set voucher amount
                    voucher_data['amount'] = party_amount
                    
                    vouchers.append(voucher_data)
                    
        except ET.ParseError as e:
            logger.warning(f"XML parsing error: {e}", exc_info=True)
        
        return vouchers
    

    def _get_element_text(self, element, path, default=''):
        """Safely get text from XML element"""
        found = element.find(path)
        if found is not None and found.text:
            return found.text.strip()
        return default

    def _get_element_decimal(self, element, path, default='0'):
        """Safely get Decimal from XML element

        SECURITY FIX: Using Decimal instead of float for financial precision.
        Prevents rounding errors in currency calculations.
        """
        text = self._get_element_text(element, path, str(default))
        try:
            return Decimal(text)
        except (ValueError, TypeError, InvalidOperation):
            try:
                return Decimal(str(default))
            except (ValueError, InvalidOperation):
                return Decimal('0')

