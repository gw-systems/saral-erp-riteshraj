from integrations.tallysync.models import TallyCostCentre, ProjectCostCentreMapping
from projects.models import ProjectCode
from difflib import SequenceMatcher
from django.db import transaction
from django.db import models


class CostCentreMatchingService:
    """Service to match Tally cost centres with ERP project codes"""
    
    def __init__(self, min_confidence=80):
        self.min_confidence = min_confidence
    
    def auto_match_all(self):
        """Auto-match all unmatched cost centres"""
        unmatched = TallyCostCentre.objects.filter(is_matched=False)
        
        total = unmatched.count()
        matched = 0
        
        for cost_centre in unmatched:
            if self.auto_match_cost_centre(cost_centre):
                matched += 1
        
        return {
            'total': total,
            'matched': matched,
            'unmatched': total - matched
        }
    
    def auto_match_cost_centre(self, cost_centre: TallyCostCentre) -> bool:
        """Try to auto-match a single cost centre"""
        
        # Method 1: Exact code match
        project = ProjectCode.objects.filter(code=cost_centre.code).first()
        
        if project:
            cost_centre.erp_project = project
            cost_centre.match_confidence = 100
            cost_centre.match_method = 'exact_code'
            cost_centre.is_matched = True
            cost_centre.save()
            return True
        
        # Method 2: Fuzzy match on client name
        if cost_centre.client_name:
            best_match = None
            best_score = 0
            
            for project in ProjectCode.objects.all():
                if not project.client_name:
                    continue
                
                score = self._similarity(
                    cost_centre.client_name.lower(),
                    project.client_name.lower()
                )
                
                if score > best_score and score >= self.min_confidence:
                    best_score = score
                    best_match = project
            
            if best_match:
                cost_centre.erp_project = best_match
                cost_centre.match_confidence = int(best_score)
                cost_centre.match_method = 'fuzzy_client'
                cost_centre.is_matched = True
                cost_centre.save()
                return True
        
        return False
    
    def _similarity(self, a: str, b: str) -> float:
        """Calculate similarity percentage between two strings"""
        return SequenceMatcher(None, a, b).ratio() * 100
    
    def get_unmatched_summary(self):
        """Get summary of unmatched cost centres"""
        unmatched = TallyCostCentre.objects.filter(is_matched=False)
        
        return {
            'total_unmatched': unmatched.count(),
            'by_company': {
                cc['company__name']: cc['count']
                for cc in unmatched.values('company__name').annotate(
                    count=models.Count('id')
                )
            }
        }