from django.db import models
from django.contrib.auth import get_user_model
from .models import ProjectCode

User = get_user_model()


class ProjectDocument(models.Model):
    """Documents/Agreements for each project"""
    
    # Link to project
    project = models.OneToOneField(
        ProjectCode,
        on_delete=models.CASCADE,
        related_name='documents',
        to_field='project_id',
        primary_key=True
    )
    
    # Agreement Documents
    project_agreement = models.FileField(
        upload_to='project_documents/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Main Agreement'
    )
    
    # Addendum - Vendor Commercial
    project_addendum_vendor = models.FileField(
        upload_to='project_documents/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Addendum (Vendor Commercial)'
    )
    
    # Addendum - Client (if applicable)
    project_addendum_client = models.FileField(
        upload_to='project_documents/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Addendum (Client)'
    )

    # Handover Document
    project_handover = models.FileField(
        upload_to='project_documents/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Handover Document'
    )
    
    # Metadata
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_project_documents'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'project_documents'
        verbose_name = 'Project Document'
        verbose_name_plural = 'Project Documents'
    
    def __str__(self):
        return f"Documents for {self.project.project_code}"
    
    def get_all_documents(self):
        """Return list of all uploaded documents with metadata"""
        docs = []
        if self.project_agreement:
            docs.append({
                'name': 'Main Agreement',
                'file': self.project_agreement,
                'field': 'project_agreement'
            })
        if self.project_addendum_vendor:
            docs.append({
                'name': 'Addendum (Vendor Commercial)',
                'file': self.project_addendum_vendor,
                'field': 'project_addendum_vendor'
            })
        if self.project_addendum_client:
            docs.append({
                'name': 'Addendum (Client)',
                'file': self.project_addendum_client,
                'field': 'project_addendum_client'
            })
        if self.project_handover:
            docs.append({
                'name': 'Handover Document',
                'file': self.project_handover,
                'field': 'project_handover'
            })
        return docs