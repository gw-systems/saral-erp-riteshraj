import hashlib
import re
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class ClientGroup(models.Model):
    """Groups related client entities under a single parent (e.g., Swara Baby + Swara Hygiene → Swara Group)"""
    name = models.CharField(max_length=150, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'client_groups'
        ordering = ['name']
        verbose_name = 'Client Group'
        verbose_name_plural = 'Client Groups'

    def __str__(self):
        return self.name


class ClientCard(models.Model):
    client_code = models.CharField(max_length=20, primary_key=True, editable=False)
    client_legal_name = models.CharField(max_length=150, unique=True)
    client_group = models.ForeignKey(
        ClientGroup, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='members',
        help_text='Group related client entities for consolidated reporting'
    )
    client_trade_name = models.CharField(max_length=100, blank=True)
    client_short_name = models.CharField(max_length=50, blank=True)
    client_gst_number = models.CharField(max_length=15, blank=True)
    client_cin_number = models.CharField(max_length=21, blank=True)
    client_pan_number = models.CharField(max_length=10, blank=True)
    client_registered_address = models.TextField(blank=True)
    client_corporate_address = models.TextField(blank=True)
    client_industry_type = models.CharField(max_length=50, blank=True)
    client_is_active = models.BooleanField(default=True)
    client_created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    client_updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'client_cards'
        ordering = ['client_legal_name']
        verbose_name = 'Client Card'
        verbose_name_plural = 'Client Cards'

    def __str__(self):
        return f"{self.client_code} - {self.client_legal_name}"

    def save(self, *args, **kwargs):
        if not self.client_code:
            self.client_code = self.generate_client_code(self.client_legal_name)
        if not self.client_short_name:
            words = self.client_legal_name.split()
            self.client_short_name = ' '.join(words[:2]) if len(words) >= 2 else self.client_legal_name
        super().save(*args, **kwargs)

    @staticmethod
    def sanitize_name(name):
        noise = [
            'pvt ltd', 'private limited', 'pvt. ltd.', 'ltd',
            'limited', 'llp', 'llc', 'inc', 'incorporated'
        ]
        clean_name = name.lower()
        for n in noise:
            clean_name = clean_name.replace(n, '')
        clean_name = re.sub(r'[^a-z0-9\s]', '', clean_name)
        clean_name = ' '.join(clean_name.split())
        return clean_name.strip()

    @staticmethod
    def generate_client_code(client_legal_name):
        clean_name = ClientCard.sanitize_name(client_legal_name)
        alphanumeric = re.sub(r'[^a-zA-Z]', '', client_legal_name)
        prefix = alphanumeric[:3].upper()
        if len(prefix) < 3:
            prefix = prefix.ljust(3, 'X')
        hash_object = hashlib.sha256(clean_name.encode())
        hash_hex = hash_object.hexdigest()
        suffix = hash_hex[-4:].upper()
        return f"{prefix}-{suffix}"


class ClientContact(models.Model):
    client_code = models.ForeignKey(ClientCard, on_delete=models.CASCADE, related_name='contacts', to_field='client_code')
    client_contact_person = models.CharField(max_length=100)
    client_contact_designation = models.CharField(max_length=100, blank=True)
    client_contact_department = models.CharField(max_length=100, blank=True, null=True)
    client_contact_phone = models.CharField(max_length=15, blank=True)
    client_contact_email = models.EmailField(blank=True)
    client_contact_is_primary = models.BooleanField(default=False)
    client_contact_is_active = models.BooleanField(default=True)
    client_contact_created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        db_table = 'client_contacts'
        ordering = ['-client_contact_is_primary', 'client_contact_person']
        verbose_name = 'Client Contact'
        verbose_name_plural = 'Client Contacts'

    def __str__(self):
        return f"{self.client_contact_person} ({self.client_code.client_legal_name}) - {self.client_contact_department}"


class ClientGST(models.Model):
    client_code = models.ForeignKey(ClientCard, on_delete=models.CASCADE, related_name='gst_entities', to_field='client_code')
    client_gst_legal_entity_name = models.CharField(max_length=150, blank=True)
    client_gst_number = models.CharField(max_length=15, unique=True)
    client_gst_state_name = models.CharField(max_length=50, blank=True)
    client_gst_registered_address = models.TextField(blank=True)
    client_gst_is_primary = models.BooleanField(default=False)
    client_gst_created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        db_table = 'client_gst'
        ordering = ['-client_gst_is_primary', 'client_gst_legal_entity_name']
        verbose_name = 'Client GST Entity'
        verbose_name_plural = 'Client GST Entities'
        unique_together = [['client_code', 'client_gst_number']]

    def __str__(self):
        return f"{self.client_gst_legal_entity_name or self.client_code.client_legal_name} - {self.client_gst_number}"


class ClientDocument(models.Model):
    client_code = models.OneToOneField(
        ClientCard, 
        on_delete=models.CASCADE, 
        primary_key=True, 
        related_name='documents', 
        to_field='client_code'
    )
    
    # CHANGED: URLField → FileField
    client_doc_certificate_of_incorporation = models.FileField(
        upload_to='client_documents/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Certificate of Incorporation'
    )
    client_doc_board_resolution = models.FileField(
        upload_to='client_documents/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Board Resolution'
    )
    client_doc_authorized_signatory = models.FileField(
        upload_to='client_documents/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Authorized Signatory Details'
    )
    
    client_doc_uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    client_doc_uploaded_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    class Meta:
        db_table = 'client_documents'
        verbose_name = 'Client Document'
        verbose_name_plural = 'Client Documents'
    
    def __str__(self):
        return f"Documents for {self.client_code.client_legal_name}"
    
    def get_all_documents(self):
        """Return list of all uploaded documents with metadata"""
        docs = []
        if self.client_doc_certificate_of_incorporation:
            docs.append({
                'name': 'Certificate of Incorporation',
                'file': self.client_doc_certificate_of_incorporation,
                'field': 'client_doc_certificate_of_incorporation'
            })
        if self.client_doc_board_resolution:
            docs.append({
                'name': 'Board Resolution',
                'file': self.client_doc_board_resolution,
                'field': 'client_doc_board_resolution'
            })
        if self.client_doc_authorized_signatory:
            docs.append({
                'name': 'Authorized Signatory',
                'file': self.client_doc_authorized_signatory,
                'field': 'client_doc_authorized_signatory'
            })
        return docs