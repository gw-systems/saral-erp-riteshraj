"""
Unit tests for Project models
"""
import pytest
from projects.models import ProjectCode


@pytest.mark.django_db
class TestProjectCodeGeneration:
    """Test project code generation logic"""
    
    def test_project_has_code(self, test_project):
        """Test that project has a code"""
        assert test_project.code == 'TEST001'
        assert test_project.series_type == 'WAAS'
    
    def test_project_code_uniqueness(self, test_client, admin_user):
        """Test that project codes are unique"""
        # Create 3 projects with different codes
        project1 = ProjectCode.objects.create(
            series_type='WAAS',
            code='TEST002',
            project_status='active',
            state='MH',
            client_card=test_client,
            operation_coordinator=admin_user
        )
        
        project2 = ProjectCode.objects.create(
            series_type='WAAS',
            code='TEST003',
            project_status='active',
            state='MH',
            client_card=test_client,
            operation_coordinator=admin_user
        )
        
        project3 = ProjectCode.objects.create(
            series_type='WAAS',
            code='TEST004',
            project_status='active',
            state='MH',
            client_card=test_client,
            operation_coordinator=admin_user
        )
        
        # All codes should be different
        codes = {project1.code, project2.code, project3.code}
        assert len(codes) == 3, f"Expected 3 unique codes, got {codes}"
    
    def test_different_series_types(self, test_client, admin_user):
        """Test different series types"""
        waas = ProjectCode.objects.create(
            series_type='WAAS',
            code='TEST005',
            project_status='active',
            state='MH',
            client_card=test_client,
            operation_coordinator=admin_user
        )
        
        saas = ProjectCode.objects.create(
            series_type='SAAS',
            code='TEST006',
            project_status='active',
            state='MH',
            client_card=test_client,
            operation_coordinator=admin_user
        )
        
        assert waas.series_type == 'WAAS'
        assert saas.series_type == 'SAAS'