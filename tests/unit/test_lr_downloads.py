import os
import tempfile
from datetime import date

import pytest
from django.urls import reverse

from operations.models_lr import LRLineItem, LorryReceipt


@pytest.fixture
def lr_sample(db, admin_user, test_project):
    lr = LorryReceipt.objects.create(
        lr_date=date(2026, 3, 14),
        project=test_project,
        from_location='Mumbai',
        to_location='Pune',
        delivery_office_address='Godamwale Delivery Hub\nGate 3, Bhosari MIDC, Pune',
        consignor_name='Dummy Consignor Pvt Ltd',
        consignor_address='Plot 18, TTC Industrial Area, Navi Mumbai',
        consignee_name='Dummy Consignee Industries',
        consignee_address='Warehouse 4, Chakan Phase 2, Pune',
        gst_paid_by='transporter',
        created_by=admin_user,
        last_modified_by=admin_user,
    )
    LRLineItem.objects.create(
        lr=lr,
        packages='12',
        description='Cartons of garments',
        actual_weight='980 KG',
        charged_weight='1000 KG',
        amount='12500',
        order=1,
    )
    return lr


@pytest.mark.django_db
def test_lr_download_docx_returns_docx_file(client, admin_user, lr_sample):
    client.force_login(admin_user)

    response = client.get(reverse('operations:lr_download_docx', args=[lr_sample.id]))

    assert response.status_code == 200
    assert response['Content-Type'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    assert f'LR_{lr_sample.lr_number}.docx' in response['Content-Disposition']

    payload = b''.join(response.streaming_content)
    assert payload[:2] == b'PK'
    response.close()


@pytest.mark.django_db
def test_lr_download_pdf_returns_pdf_file(client, admin_user, lr_sample, monkeypatch):
    client.force_login(admin_user)

    fd, pdf_path = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    with open(pdf_path, 'wb') as handle:
        handle.write(b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n')

    monkeypatch.setattr('operations.services.lr_docx_generator.generate_lr_pdf', lambda lr, items: pdf_path)

    response = client.get(reverse('operations:lr_download_pdf', args=[lr_sample.id]))

    try:
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert f'LR_{lr_sample.lr_number}.pdf' in response['Content-Disposition']

        payload = b''.join(response.streaming_content)
        assert payload.startswith(b'%PDF')
    finally:
        response.close()
