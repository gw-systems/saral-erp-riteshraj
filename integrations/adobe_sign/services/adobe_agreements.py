"""
Adobe Sign Agreement Service
Enhanced agreement management with improved workflow
"""

import requests
import logging
import time
from django.conf import settings
from .adobe_auth import AdobeAuthService
from integrations.adobe_sign.exceptions import AdobeAgreementError

logger = logging.getLogger(__name__)


class AdobeAgreementService:
    """
    Service for Adobe Sign agreement operations
    Supports AUTHORING state for approval workflow and enhanced configuration
    """
    BASE_URL = getattr(settings, 'ADOBE_SIGN_BASE_URL', 'https://api.in1.adobesign.com/api/rest/v6').rstrip('/')

    @staticmethod
    def create_agreement_for_authoring(
        transient_document_id,
        agreement_name,
        signers_data,
        ccs=None,
        message='',
        days_until_signing_deadline=30,
        reminder_frequency='EVERY_OTHER_DAY',
        form_fields=None,
        obo_email=None,
        post_sign_redirect_url=None
    ):
        """
        Create an agreement in AUTHORING state (not sent yet)
        This allows admin to review/edit before sending to clients

        Args:
            transient_document_id: ID from upload_transient_document
            agreement_name: Name of the agreement
            signers_data: list of dicts with 'name', 'email', 'order', 'role'
            ccs: list of CC email strings (optional)
            message: Custom message shown to signers
            days_until_signing_deadline: Days before agreement expires
            reminder_frequency: How often to remind signers
            form_fields: list of form field definitions with coordinates (optional)
            obo_email: On-Behalf-Of email
            post_sign_redirect_url: URL to redirect signer after signing (optional)

        Returns:
            str: Adobe agreement ID

        Raises:
            AdobeAgreementError: If creation fails
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        # Build participant sets
        participant_sets_info = []
        for signer in signers_data:
            # securityOption must be inside memberInfos (not at participant set level).
            # NONE = no identity check — signing URL works without Adobe login,
            # required for embedded iframe signing inside the ERP.
            member_info = {
                "email": signer['email'],
                "securityOption": {"authenticationMethod": "NONE"},
            }

            # Add name if provided
            if signer.get('name'):
                member_info["name"] = signer['name']

            # Add private message if provided
            if signer.get('private_message'):
                member_info["privateMessage"] = signer['private_message']

            participant_set = {
                "memberInfos": [member_info],
                "order": signer.get('order', 1),
                "role": signer.get('role', 'SIGNER'),
            }
            participant_sets_info.append(participant_set)

        # Build payload
        payload = {
            "fileInfos": [{
                "transientDocumentId": transient_document_id
            }],
            "name": agreement_name,
            "participantSetsInfo": participant_sets_info,
            "signatureType": "ESIGN",
            "state": "AUTHORING",
            "emailOption": {
                "sendOptions": {
                    "initEmails": "ALL",  # Send signing request emails when transitioned to IN_PROCESS
                    "completionEmails": "ALL"
                }
            }
        }

        # IMPORTANT: Do NOT add form fields when creating in AUTHORING state
        # Adobe Sign does not support formFieldLayerTemplates for AUTHORING agreements
        # Signature fields must be added through the authoring UI or when sending
        # if form_fields:
        #     payload["formFieldLayerTemplates"] = [{
        #         "formFields": form_fields
        #     }]

        # Add optional fields
        if message:
            payload["message"] = message

        if ccs:
            payload["ccs"] = [{"email": email} for email in ccs]

        # Set expiration
        if days_until_signing_deadline:
            payload["daysUntilSigningDeadline"] = days_until_signing_deadline

        # Set reminder frequency
        if reminder_frequency:
            payload["reminderFrequency"] = reminder_frequency

        # Redirect signer back to ERP after signing
        if post_sign_redirect_url:
            payload["postSignOption"] = {
                "redirectUrl": post_sign_redirect_url,
                "redirectDelay": 3
            }

        try:
            logger.info(f"Creating agreement in AUTHORING state: '{agreement_name}'")
            logger.debug(f"Payload: {payload}")

            response = requests.post(url, headers=headers, json=payload, timeout=60)

            if not response.ok:
                logger.error(f"Adobe Error Response: {response.status_code} - {response.text}")

            response.raise_for_status()

            resp_json = response.json()
            agreement_id = resp_json.get('id')

            if not agreement_id:
                raise AdobeAgreementError(f"No agreement ID in response: {resp_json}")

            logger.info(f"Agreement created in AUTHORING state. ID: {agreement_id}")
            return agreement_id

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create agreement: {e}")
            raise AdobeAgreementError(f"Failed to create agreement: {str(e)}")

    @staticmethod
    def put_form_fields(agreement_id, form_fields, obo_email=None):
        """
        Add/replace form fields on an agreement in AUTHORING state.

        Adobe Sign v6 requires:
        1. Poll GET /agreements/{id} until status != DOCUMENTS_NOT_YET_PROCESSED
        2. GET /agreements/{id}/formFields to obtain the current ETag
        3. PUT /agreements/{id}/formFields with If-Match: {etag} header

        Raises:
            AdobeAgreementError: If the request fails after all retries
        """
        base_url = AdobeAgreementService.BASE_URL
        headers = AdobeAuthService.get_headers(obo_email=obo_email)
        max_poll_attempts = 12
        poll_delay = 5  # seconds

        # Step 1: Poll until Adobe finishes processing the uploaded document
        logger.info(f"Waiting for agreement {agreement_id} document to finish processing...")
        agreement_status = None
        for poll_attempt in range(1, max_poll_attempts + 1):
            try:
                status_resp = requests.get(
                    f"{base_url}/agreements/{agreement_id}",
                    headers=headers,
                    timeout=30
                )
                status_resp.raise_for_status()
                agreement_status = status_resp.json().get('status', '')
                logger.info(f"Agreement status (poll {poll_attempt}/{max_poll_attempts}): {agreement_status}")
                if agreement_status != 'DOCUMENTS_NOT_YET_PROCESSED':
                    break
                if poll_attempt < max_poll_attempts:
                    logger.warning(f"Document still processing, retrying in {poll_delay}s...")
                    time.sleep(poll_delay)
                else:
                    raise AdobeAgreementError(
                        f"Agreement {agreement_id} still in DOCUMENTS_NOT_YET_PROCESSED after {max_poll_attempts} attempts"
                    )
            except requests.exceptions.RequestException as e:
                raise AdobeAgreementError(f"Failed to poll agreement status: {str(e)}")

        # Verify agreement is still in AUTHORING state (required for PUT /formFields)
        if agreement_status and agreement_status != 'AUTHORING':
            raise AdobeAgreementError(
                f"Agreement {agreement_id} is in {agreement_status} state, not AUTHORING. "
                f"Form fields can only be applied to agreements in AUTHORING state."
            )

        # Step 2: GET /formFields to obtain ETag and existing fields required for the PUT.
        # Adobe Sign PUT /formFields replaces ALL fields, so we must include existing
        # imported fields (e.g. text fields from the PDF template) alongside our new ones.
        logger.info(f"[put_form_fields] Fetching ETag for agreement {agreement_id}...")
        existing_fields = []
        try:
            get_resp = requests.get(
                f"{base_url}/agreements/{agreement_id}/formFields",
                headers=headers,
                timeout=30
            )
            get_resp.raise_for_status()
            etag = get_resp.headers.get('ETag') or get_resp.headers.get('etag')
            if not etag:
                etag = next((v for k, v in get_resp.headers.items() if k.lower() == 'etag'), None)
            existing_fields = get_resp.json().get('fields', [])
            logger.info(f"[put_form_fields] ETag found. Existing fields from Adobe: {len(existing_fields)}.")
        except requests.exceptions.RequestException as e:
            raise AdobeAgreementError(f"Failed to get formFields ETag: {str(e)}")

        # Adobe Sign v6 PUT /formFields is strict: it rejects any property not in its
        # internal whitelist, even ones returned by GET (e.g. signerIndex, urlOverridable,
        # currency, origin).  The error message incorrectly says "Property: inputType" but
        # the real cause is unrecognised round-tripped properties on imported fields.
        # Safest approach: only pass the spec-documented writable properties.
        _ALLOWED_FIELD_KEYS = {
            'name', 'locations', 'contentType', 'inputType', 'assignee', 'required', 'visible',
            'readOnly', 'defaultValue', 'displayLabel', 'tooltip', 'alignment',
            'fontColor', 'fontName', 'fontSize', 'backgroundColor', 'borderColor',
            'borderStyle', 'borderWidth', 'masked', 'maskingText', 'radioCheckType',
            'displayFormat', 'displayFormatType', 'validation', 'validationData',
            'validationErrMsg', 'minLength', 'maxLength', 'minValue', 'maxValue',
            'calculated', 'valueExpression', 'conditionalAction', 'hyperlink',
            'hiddenOptions', 'visibleOptions',
        }

        def _sanitise_field(f):
            return {k: v for k, v in f.items() if k in _ALLOWED_FIELD_KEYS}

        # Only keep existing fields that Adobe actually accepts in PUT.
        # Whitelist approach: only pass contentTypes we know are safe to round-trip.
        # Adobe imports PDF hyperlinks as PDFLink fields (no contentType) and PDF acroforms
        # as DATA fields — both cause 400 INVALID_FORM_FIELD_PROPERTY if included in PUT.
        # We also drop any prior signature blocks (replaced by new ones from JS).
        _ACCEPTED_CONTENT_TYPES = {
            'TEXT', 'MULTILINE', 'PASSWORD', 'CHECKBOX', 'RADIO', 'LIST', 'DROP_DOWN',
            'TITLE', 'LABEL', 'SIGNATURE', 'SIGNATURE_BLOCK', 'DIGITAL_SIGNATURE',
            'STAMP', 'INITIALS',
        }
        new_names = {f['name'] for f in form_fields}
        retained_existing = [
            _sanitise_field(f)
            for f in existing_fields
            if f.get('name') not in new_names
            and f.get('contentType') in _ACCEPTED_CONTENT_TYPES
            and f.get('name')
            and f.get('locations')
        ]
        merged_fields = retained_existing + [_sanitise_field(f) for f in form_fields]

        # Step 3: PUT /formFields with If-Match header
        put_url = f"{base_url}/agreements/{agreement_id}/formFields"
        put_headers = dict(headers)
        if etag:
            put_headers['If-Match'] = etag
        payload = {"fields": merged_fields}

        import json as _json
        for _f in merged_fields:
            _locs = (_f.get('locations') or [{}])
            _loc = _locs[0] if _locs else {}
            logger.warning(f"[put_form_fields] SENDING field='{_f.get('name')}' ct={_f.get('contentType')} top={_loc.get('top')} left={_loc.get('left')} w={_loc.get('width')} h={_loc.get('height')} pg={_loc.get('pageNumber')}")
        logger.info(f"[put_form_fields] Putting {len(merged_fields)} fields ({len(retained_existing)} existing + {len(form_fields)} new) on {agreement_id}.")
        try:
            response = requests.put(put_url, headers=put_headers, json=payload, timeout=60)

            if not response.ok:
                logger.error(f"Adobe Error (put_form_fields): {response.status_code} - {response.text}")

            response.raise_for_status()
            logger.info(f"[put_form_fields] Success.")
            # Verify: GET fields back and log locations to confirm coordinate system
            import json as _json
            verify_resp = requests.get(put_url, headers=headers, timeout=30)
            if verify_resp.ok:
                for _f in verify_resp.json().get('fields', []):
                    _locs = _f.get('locations') or _f.get('location') or []
                    if not isinstance(_locs, list): _locs = [_locs]
                    for _loc in _locs:
                        logger.warning(f"[put_form_fields] VERIFY field='{_f.get('name')}' ct={_f.get('contentType')} loc={_json.dumps(_loc)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to put form fields: {e}")
            raise AdobeAgreementError(f"Failed to put form fields: {str(e)}")

    @staticmethod
    def send_agreement(agreement_id, obo_email=None):
        """
        Transition agreement from AUTHORING to IN_PROCESS.
        Sends the document to signers.

        PUT /agreements/{id}/state requires an If-Match ETag header (v6).
        Fetch it first via GET /agreements/{id}.

        Args:
            agreement_id: Adobe agreement ID
            obo_email: Optional On-Behalf-Of email

        Returns:
            bool: True if sent successfully

        Raises:
            AdobeAgreementError: If sending fails
        """
        base_url = AdobeAgreementService.BASE_URL
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        # Fetch current agreement status and ETag — required by PUT /state in v6
        try:
            get_resp = requests.get(
                f"{base_url}/agreements/{agreement_id}",
                headers=headers,
                timeout=30
            )
            get_resp.raise_for_status()
            current_status = get_resp.json().get('status', '')
            etag = next((v for k, v in get_resp.headers.items() if k.lower() == 'etag'), None)
            logger.info(f"Agreement {agreement_id} current status: {current_status}, ETag: {etag}")
        except requests.exceptions.RequestException as e:
            raise AdobeAgreementError(f"Failed to fetch agreement ETag: {str(e)}")

        # Safety check: if already OUT_FOR_SIGNATURE, skip the state transition
        # This prevents the double-send that was stripping form fields
        if current_status == 'OUT_FOR_SIGNATURE':
            logger.warning(
                f"Agreement {agreement_id} already OUT_FOR_SIGNATURE, skipping state transition"
            )
            return True

        put_headers = dict(headers)
        if etag:
            put_headers['If-Match'] = etag

        try:
            logger.info(f"Sending agreement {agreement_id} (AUTHORING -> IN_PROCESS)")
            response = requests.put(
                f"{base_url}/agreements/{agreement_id}/state",
                headers=put_headers,
                json={"state": "IN_PROCESS"},
                timeout=30
            )

            if not response.ok:
                logger.error(f"Adobe Error Response: {response.status_code} - {response.text}")

            response.raise_for_status()

            logger.info(f"Agreement {agreement_id} sent successfully!")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send agreement: {e}")
            raise AdobeAgreementError(f"Failed to send agreement: {str(e)}")

    @staticmethod
    def get_agreement_status(agreement_id, obo_email=None):
        """
        Get current status of an agreement from Adobe

        Args:
            agreement_id: Adobe agreement ID
            obo_email: Optional On-Behalf-Of email

        Returns:
            str: Agreement status

        Raises:
            AdobeAgreementError: If retrieval fails
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            return response.json().get('status')

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get status: {e}")
            raise AdobeAgreementError(f"Failed to get status: {str(e)}")

    @staticmethod
    def get_agreement_details(agreement_id, obo_email=None):
        """
        Get full agreement details from Adobe

        Args:
            agreement_id: Adobe agreement ID
            obo_email: Optional On-Behalf-Of email

        Returns:
            dict: Agreement details

        Raises:
            AdobeAgreementError: If retrieval fails
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get agreement details: {e}")
            raise AdobeAgreementError(f"Failed to get agreement details: {str(e)}")

    @staticmethod
    def get_authoring_url(agreement_id, obo_email=None):
        """
        Get URL for Adobe Sign authoring interface
        Allows adding/editing signature fields manually if needed

        Args:
            agreement_id: Adobe agreement ID
            obo_email: Optional On-Behalf-Of email

        Returns:
            str: Authoring URL

        Raises:
            AdobeAgreementError: If retrieval fails
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}/views"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        payload = {
            "name": "AUTHORING"
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.ok:
                data = response.json()
                # Adobe returns agreementViewList array
                view_list = data.get('agreementViewList', [])
                if view_list:
                    authoring_url = view_list[0].get('url')
                    if authoring_url:
                        return authoring_url

                # Fallback to direct url field
                authoring_url = data.get('url')
                if authoring_url:
                    return authoring_url

            logger.error(f"Failed to get authoring URL: {response.status_code} {response.text}")
            raise AdobeAgreementError(f"Failed to get authoring URL: {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Authoring URL exception: {e}")
            raise AdobeAgreementError(f"Failed to get authoring URL: {str(e)}")

    @staticmethod
    def get_signing_url(agreement_id, signer_email=None, obo_email=None):
        """
        Get signing URL for a specific signer.

        After send_agreement() transitions to IN_PROCESS, Adobe needs time
        to process before signing URLs become available. This method polls
        with increasing delays to handle that latency.

        Args:
            agreement_id: Adobe agreement ID
            signer_email: Email of signer (optional, gets first if not specified)
            obo_email: Optional On-Behalf-Of email

        Returns:
            str: Signing URL or None
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}/signingUrls"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        max_retries = 6
        # Increasing delays: 3s, 4s, 5s, 6s, 7s (total ~25s wait)
        base_delay = 3

        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()

                data = response.json()
                logger.info(f"Signing URL attempt {attempt + 1}: response keys={list(data.keys())}")

                if 'signingUrlSetInfos' in data and data['signingUrlSetInfos']:
                    urls = data['signingUrlSetInfos'][0].get('signingUrls', [])
                    logger.info(f"Signing URL attempt {attempt + 1}: found {len(urls)} URLs")

                    # If specific email requested, find their URL
                    if signer_email:
                        for url_info in urls:
                            if url_info.get('email', '').lower() == signer_email.lower():
                                logger.info(f"Found signing URL for {signer_email}")
                                return url_info.get('esignUrl')
                        # Email not found in available URLs - log available emails
                        available = [u.get('email', '?') for u in urls]
                        logger.warning(f"Signing URL attempt {attempt + 1}: signer {signer_email} not in {available}")

                    # Otherwise return first available
                    elif urls:
                        return urls[0].get('esignUrl')

            except Exception as e:
                logger.warning(f"Signing URL attempt {attempt + 1}/{max_retries}: {e}")

            if attempt < max_retries - 1:
                time.sleep(base_delay + attempt)

        logger.error(f"Failed to get signing URL after {max_retries} attempts for agreement {agreement_id}")
        return None

    @staticmethod
    def get_document_view_url(agreement_id, obo_email=None):
        """
        Get URL for viewing the document (read-only)

        Args:
            agreement_id: Adobe agreement ID
            obo_email: Optional On-Behalf-Of email

        Returns:
            str: Document view URL or None
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}/views"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        payload = {
            "name": "DOCUMENT"  # Read-only document view
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.ok:
                data = response.json()
                view_list = data.get('agreementViewList', [])
                if view_list:
                    doc_url = view_list[0].get('url')
                    if doc_url:
                        logger.info(f"Got document view URL for agreement {agreement_id}")
                        return doc_url

                # Fallback to direct url field
                return data.get('url')

            logger.warning(f"Failed to get document view URL: {response.status_code}")
            return None

        except Exception as e:
            logger.error(f"Failed to get document view URL: {e}")
            return None

    @staticmethod
    def get_agreement_events(agreement_id, obo_email=None):
        """
        Get audit trail/event list for an agreement

        Args:
            agreement_id: Adobe agreement ID
            obo_email: Optional On-Behalf-Of email

        Returns:
            list: List of event dictionaries
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}/events"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            return response.json().get('events', [])

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get agreement events: {e}")
            return []

    @staticmethod
    def has_director_signed(agreement_id, director_email, obo_email=None):
        """
        Check if the director has completed signing

        Args:
            agreement_id: Adobe agreement ID
            director_email: Director's email address
            obo_email: Optional On-Behalf-Of email

        Returns:
            bool: True if director has signed
        """
        if not director_email:
            return False

        events = AdobeAgreementService.get_agreement_events(agreement_id, obo_email=obo_email)

        for event in events:
            event_type = event.get('type', '')
            participant_email = event.get('participantEmail', '').lower()

            # Check for ACTION_COMPLETED event by director
            if event_type == 'ACTION_COMPLETED' and participant_email == director_email.lower():
                logger.info(f"Director {director_email} has signed agreement {agreement_id}")
                return True

        return False

    @staticmethod
    def get_signed_document(agreement_id, obo_email=None):
        """
        Download the signed PDF document

        Args:
            agreement_id: Adobe agreement ID
            obo_email: Optional On-Behalf-Of email

        Returns:
            bytes: PDF file content

        Raises:
            AdobeAgreementError: If download fails
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}/combinedDocument"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)
        headers['Accept'] = 'application/pdf'

        try:
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()

            logger.info(f"Downloaded signed document for agreement {agreement_id}")
            return response.content

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download document: {e}")
            raise AdobeAgreementError(f"Failed to download document: {str(e)}")

    @staticmethod
    def cancel_agreement(agreement_id, reason="Cancelled", notify_signers=False, obo_email=None):
        """
        Cancel an agreement

        Args:
            agreement_id: Adobe agreement ID
            reason: Cancellation reason
            notify_signers: Whether to notify signers
            obo_email: Optional On-Behalf-Of email

        Returns:
            bool: True if cancelled successfully

        Raises:
            AdobeAgreementError: If cancellation fails
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}/state"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        payload = {
            "state": "CANCELLED",
            "agreementCancellationInfo": {
                "comment": reason,
                "notifyOthers": notify_signers
            }
        }

        # Fetch ETag — required by PUT /state in v6
        try:
            get_resp = requests.get(
                f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}",
                headers=headers,
                timeout=30,
            )
            get_resp.raise_for_status()
            etag = next((v for k, v in get_resp.headers.items() if k.lower() == 'etag'), None)
        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not fetch ETag before cancel: {e}")
            etag = None

        put_headers = dict(headers)
        if etag:
            put_headers['If-Match'] = etag

        try:
            response = requests.put(url, headers=put_headers, json=payload, timeout=30)
            response.raise_for_status()

            logger.info(f"Agreement {agreement_id} cancelled: {reason}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to cancel agreement: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Adobe response: {e.response.text}")
            raise AdobeAgreementError(f"Failed to cancel agreement: {str(e)}")

    @staticmethod
    def remind_signers(agreement_id, comment='', obo_email=None):
        """
        Send reminder to pending signers

        Args:
            agreement_id: Adobe agreement ID
            comment: Optional reminder message
            obo_email: Optional On-Behalf-Of email

        Returns:
            bool: True if reminder sent successfully

        Raises:
            AdobeAgreementError: If reminder fails
        """
        url = f"{AdobeAgreementService.BASE_URL}/agreements/{agreement_id}/reminders"
        headers = AdobeAuthService.get_headers(obo_email=obo_email)

        payload = {}
        if comment:
            payload['comment'] = comment

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            logger.info(f"Reminder sent for agreement {agreement_id}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send reminder: {e}")
            raise AdobeAgreementError(f"Failed to send reminder: {str(e)}")

    @staticmethod
    def get_signing_participants(agreement_id, obo_email=None):
        """
        Get list of participants and their signing status

        Args:
            agreement_id: Adobe agreement ID
            obo_email: Optional On-Behalf-Of email

        Returns:
            list: List of participant dictionaries with status

        Raises:
            AdobeAgreementError: If retrieval fails
        """
        details = AdobeAgreementService.get_agreement_details(agreement_id, obo_email=obo_email)

        participants = []
        participant_sets = details.get('participantSetsInfo', [])

        for pset in participant_sets:
            for member in pset.get('memberInfos', []):
                participants.append({
                    'email': member.get('email'),
                    'name': member.get('name', ''),
                    'status': pset.get('status', 'UNKNOWN'),
                    'order': pset.get('order', 0),
                    'role': pset.get('role', 'SIGNER')
                })

        return participants
