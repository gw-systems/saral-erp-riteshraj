from django.core.management.base import BaseCommand
from integrations.tallysync.services.matching_service import CostCentreMatchingService
from integrations.tallysync.models import TallyCostCentre


class Command(BaseCommand):
    help = 'Match Tally cost centres with ERP project codes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-confidence',
            type=int,
            default=80,
            help='Minimum confidence score for fuzzy matching (0-100)'
        )

    def handle(self, *args, **options):
        min_confidence = options['min_confidence']
        service = CostCentreMatchingService(min_confidence=min_confidence)
        
        self.stdout.write(f"\n🔍 Starting cost centre matching (min confidence: {min_confidence}%)")
        
        # Show current status
        total = TallyCostCentre.objects.count()
        matched = TallyCostCentre.objects.filter(is_matched=True).count()
        
        self.stdout.write(f"\n📊 Current status:")
        self.stdout.write(f"   Total cost centres: {total}")
        self.stdout.write(f"   Already matched: {matched}")
        self.stdout.write(f"   Unmatched: {total - matched}")
        
        # Run auto-matching
        self.stdout.write(f"\n⚙️  Running auto-match...")
        result = service.auto_match_all()
        
        self.stdout.write(f"\n✅ Matching complete:")
        self.stdout.write(self.style.SUCCESS(f"   Newly matched: {result['matched']}"))
        self.stdout.write(f"   Still unmatched: {result['unmatched']}")
        
        # Show breakdown by method
        exact_matches = TallyCostCentre.objects.filter(match_method='exact_code').count()
        fuzzy_matches = TallyCostCentre.objects.filter(match_method='fuzzy_client').count()
        
        self.stdout.write(f"\n📈 Match breakdown:")
        self.stdout.write(f"   Exact code matches: {exact_matches}")
        self.stdout.write(f"   Fuzzy client matches: {fuzzy_matches}")
        
        # Show some examples
        if result['matched'] > 0:
            self.stdout.write(f"\n📝 Sample matches:")
            for cc in TallyCostCentre.objects.filter(is_matched=True)[:5]:
                self.stdout.write(
                    f"   {cc.code} ({cc.client_name}) → "
                    f"{cc.erp_project.project_code if cc.erp_project else 'None'} "
                    f"({cc.match_confidence}% confidence)"
                )