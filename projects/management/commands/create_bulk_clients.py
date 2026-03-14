"""
Management command to bulk create ClientCard records
Usage: python manage.py create_bulk_clients
"""
from django.core.management.base import BaseCommand
from projects.models import ClientCard


class Command(BaseCommand):
    help = 'Bulk create ClientCard records for predefined company names'

    def handle(self, *args, **options):
        # List of company names (using as both legal_name and short_name)
        company_names = [
            '75F',
            'A R Traders',
            'AAK',
            'Ace Kreamers',
            'Advanced Crushing Engineers',
            'Agarwal Earthmoving',
            'Airconditioning Spares Centre',
            'All Arch',
            'Ambica Steels',
            'Antyodaya Ujas',
            'APS Trans',
            'Aropat Infra',
            'Arora Speciality',
            'Asan Packaging',
            'Aumjay',
            'Auroglobal',
            'Aussan Laboratories',
            'Awishkar Associates',
            'Backuplane E-Commerce Ventures',
            'Baheti Tech',
            'Banga Solar',
            'Blackposh Group',
            'Bommidi Industries',
            'Broadbent',
            'Broekman Logistics',
            'Buick Polymers',
            'Callisto Exports',
            'Canbara Industries',
            'Casah Associates',
            'Catalysts Bio Technologies',
            'Cature Shield',
            'CCI India',
            'Cenergy Solutions',
            'Ceyenar Chemicals',
            'CH101 Market',
            'Ciessem Industries',
            'Clean Water & Energy Trust',
            'Cocreate Global [Scimplify]',
            'Compomall',
            'CPL Aromas',
            'Dhampur Bio',
            'Digitalist Techmedia',
            'DKSH',
            'Duramaterials',
            'Earth Syscom',
            'Easemor',
            'Edata Ventures',
            'EIS Techinfra Solutions',
            'Elephanteer',
            'ELXR Beverages',
            'Emami Agrotech Limited',
            'Enersync',
            'Fenchem India',
            'Fibre Glass Insulation',
            'Fivebro Water Services',
            'Fore Excel',
            'Fuxion International',
            'Genau Manufacturing',
            'Glazewall Traders',
            'Global Trade Solutions',
            'Globus Rubchem',
            'Glofara Health',
            'Greaves Cotton',
            'Haryana Leather Chemicals',
            'HCT Solution',
            'Honestinnovations',
            'I Think Food',
            'Iaza Pharma',
            'Ilan Globe',
            'Indiwheel logisol',
            'Indspiration Foods',
            'Infinity Toy Tronics',
            'Innoviti Technologies',
            'Iridium Chemical',
            'Ishan Infotech',
            'Iskraemeco India',
            'Jainex Corporate Gifts',
            'Jayanthi Trade Links',
            'JCB India',
            'K K Chem',
            'Kaleido Print',
            'Kaomni Trading',
            'Kataline',
            'Klingelnberg',
            'KMSN Enterprise',
            'Konkem Industries',
            'Krafted Bite',
            'Kriasha Enterprises',
            'Krishnendu Enterprises',
            'KRISID Trading',
            'Kukdo Chemical',
            'KVM Imperial',
            'Laridae SCS',
            'Litconik Energies',
            'Lite Bite Foods',
            'Lokya Enterprises',
            'Mahindra TEQO',
            'Makhayo Foods',
            'MM Plastics',
            'Msg Sports Infratek',
            'MTM Workplace Solutions',
            'Neodash Technologies',
            'Neosym Industry',
            'Nexon Gifts',
            'Nexten Brands',
            'Noguilt Fitness',
            'Novapro Cooling Solutions',
            'Nutrilo Chikki & Snacks',
            'Nutrimatter Labs',
            'Nyka Events',
            'Oagri Farm',
            'OFB Tech',
            'Optibiotix',
            'Orb Energy',
            'Paras Polymers',
            'Pragya Refrigeration',
            'Primocraft Solutions',
            'Procart Industrial Solutions',
            'Q Ralling',
            'QMS',
            'Ratnagiri Impex [Navata SCS]',
            'Realtime Biometrics',
            'Reliance Decor',
            'Rightside Story',
            'Roofsol Energy',
            'Roseate Enterprise',
            'Samaah Techno',
            'Sampoorti Fartec',
            'Sanwud Surfaces',
            'Satvika Bio Foods',
            'SB Agro',
            'Scan Global Logistics',
            'Scimplify',
            'Security Engineers',
            'Select Technologies',
            'SF Dyes',
            'Shashi Enterprises',
            'Sheth Trading Corporation',
            'Shree Maruti',
            'Skytek Technologies [Kaleido Print]',
            'Somochem India',
            'Speciality Restaurants',
            'Spigen India',
            'SS Ecocare',
            'Staarglo Digital Technologies',
            'Sterimed Kochi',
            'Sun Infonet',
            'Sunstore',
            'Swara Baby Products',
            'Swara Hygiene Products',
            'Synco Industries Ltd',
            'Syndicate Innovations',
            'TAK 5 Snacking',
            'Tawazon Chemicals',
            'Tescom Business Solutions LLP',
            'Thermofriz Lubricant',
            'Tibrewala Electronics',
            'Top Reach Solutions',
            'Tranquil',
            'Transcon Electronic',
            'Truuchem Tech',
            'Uniclan Healthcare',
            'Uniorbis LLP',
            'Vadham Teas',
            'Valeur Fabtex',
            'Vendiman',
            'Verdical Solutions India',
            'Vihana Health Care',
            'VK Agriculture',
            'VK Packwell',
            'VSL Logistics',
            'Wolkus Technology',
            'Zomato Entertainment',
            'Zunroof Tech',
        ]

        created_count = 0
        skipped_count = 0
        error_count = 0

        self.stdout.write(self.style.NOTICE(f'Starting bulk client creation for {len(company_names)} companies...\n'))

        for company_name in company_names:
            try:
                # Check if already exists
                if ClientCard.objects.filter(client_legal_name=company_name).exists():
                    self.stdout.write(self.style.WARNING(f'⚠️  Skipped: {company_name} (already exists)'))
                    skipped_count += 1
                    continue

                # Create new ClientCard
                client = ClientCard.objects.create(
                    client_legal_name=company_name,
                    client_short_name=company_name,  # Using same name for now
                    client_is_active=True
                )

                self.stdout.write(self.style.SUCCESS(f'✅ Created: {company_name} (Code: {client.client_code})'))
                created_count += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Error: {company_name} - {str(e)}'))
                error_count += 1

        # Summary
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS(f'✅ Created: {created_count}'))
        self.stdout.write(self.style.WARNING(f'⚠️  Skipped: {skipped_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'❌ Errors: {error_count}'))
        self.stdout.write(f'📊 Total: {len(company_names)}')
        self.stdout.write('='*70)
