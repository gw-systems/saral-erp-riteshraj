from django import forms
from .models_document import ProjectDocument


class ProjectDocumentForm(forms.ModelForm):
    class Meta:
        model = ProjectDocument
        fields = [
            'project_agreement',
            'project_addendum_vendor',
            'project_addendum_client',
            'project_handover',
        ]
        widgets = {
            'project_agreement': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'project_addendum_vendor': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'project_addendum_client': forms.FileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
            'project_handover': forms.FileInput(attrs={ 
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500',
                'accept': '.pdf,.jpg,.jpeg,.png'
            }),
        }
        labels = {
            'project_agreement': 'Main Agreement',
            'project_addendum_vendor': 'Addendum (Vendor Commercial)',
            'project_addendum_client': 'Addendum (Client - if applicable)',
            'project_handover': 'Handover Document', 
        }