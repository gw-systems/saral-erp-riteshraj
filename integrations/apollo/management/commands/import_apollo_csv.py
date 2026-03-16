import csv
from datetime import datetime
from hashlib import sha1
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from integrations.apollo.models import ApolloCampaign, ApolloMessage


class Command(BaseCommand):
    help = 'Import Apollo historical CSV exports into ApolloCampaign and ApolloMessage tables.'

    REQUIRED_COLUMNS = {
        'Message ID',
        'Recipient',
        'Campaign Name',
        'Status',
        'Email Status',
        'Sent At',
    }

    def add_arguments(self, parser):
        parser.add_argument('csv_path', help='Path to the Apollo CSV export.')
        parser.add_argument(
            '--replace-existing',
            action='store_true',
            help='Delete existing Apollo campaign/message rows before importing the CSV.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Parse and validate the CSV, then roll back the database transaction.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Optional number of CSV rows to process for testing.',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=2000,
            help='Number of CSV rows to process per database batch.',
        )

    def handle(self, *args, **options):
        csv_path = Path(options['csv_path']).expanduser()
        if not csv_path.exists():
            raise CommandError(f'CSV file not found: {csv_path}')

        stats = {
            'rows_read': 0,
            'rows_skipped': 0,
            'duplicate_rows': 0,
            'campaigns_created': 0,
            'campaigns_updated': 0,
            'messages_created': 0,
            'messages_updated': 0,
        }
        limit = options['limit']
        batch_size = max(1, options['batch_size'])
        batch_rows = []
        batch_campaign_payloads = {}
        campaign_cache = {}

        with transaction.atomic():
            if options['replace_existing']:
                deleted_messages, _ = ApolloMessage.objects.all().delete()
                deleted_campaigns, _ = ApolloCampaign.objects.all().delete()
                self.stdout.write(
                    self.style.WARNING(
                        f'Cleared existing Apollo data: {deleted_messages} message rows, {deleted_campaigns} campaign rows.'
                    )
                )

            fetch_existing = not options['replace_existing']

            with csv_path.open('r', encoding='utf-8-sig', newline='') as csv_file:
                reader = csv.DictReader(csv_file)
                self._validate_columns(reader.fieldnames or [])

                for row_number, raw_row in enumerate(reader, start=2):
                    if limit is not None and stats['rows_read'] >= limit:
                        break

                    stats['rows_read'] += 1
                    normalized_row = self._normalize_row(raw_row)
                    message_id = normalized_row['message_id']
                    if not message_id:
                        stats['rows_skipped'] += 1
                        self.stderr.write(f'Skipping row {row_number}: missing Message ID')
                        continue

                    campaign_id = ''
                    if normalized_row['campaign_name']:
                        campaign_id = self._campaign_key(normalized_row['campaign_name'])
                        if campaign_id not in campaign_cache:
                            batch_campaign_payloads[campaign_id] = {
                                'apollo_id': campaign_id,
                                'name': normalized_row['campaign_name'],
                                'raw_data': {
                                    'source': 'csv',
                                    'campaign_name': normalized_row['campaign_name'],
                                    'sample_row': {
                                        'Message ID': raw_row.get('Message ID'),
                                        'Subject': raw_row.get('Subject'),
                                    },
                                },
                            }

                    batch_rows.append({
                        'normalized': normalized_row,
                        'raw_row': raw_row,
                        'campaign_id': campaign_id,
                    })

                    if len(batch_rows) >= batch_size:
                        self._flush_batch(
                            batch_rows,
                            batch_campaign_payloads,
                            campaign_cache,
                            stats,
                            fetch_existing=fetch_existing,
                        )
                        batch_rows = []
                        batch_campaign_payloads = {}
                        fetch_existing = True
                        self.stdout.write(f"Processed {stats['rows_read']} CSV rows...")

                if batch_rows:
                    self._flush_batch(
                        batch_rows,
                        batch_campaign_payloads,
                        campaign_cache,
                        stats,
                        fetch_existing=fetch_existing,
                    )

            if options['dry_run']:
                transaction.set_rollback(True)

        mode = 'Dry run complete' if options['dry_run'] else 'Import complete'
        self.stdout.write(self.style.SUCCESS(mode))
        for key, value in stats.items():
            self.stdout.write(f'{key}: {value}')

    def _validate_columns(self, fieldnames):
        missing = sorted(self.REQUIRED_COLUMNS - set(fieldnames))
        if missing:
            raise CommandError(f'CSV is missing required columns: {", ".join(missing)}')

    def _normalize_row(self, raw_row):
        opens = self._parse_int(raw_row.get('Opens'))
        return {
            'message_id': self._clean(raw_row.get('Message ID')),
            'first_name': self._clean(raw_row.get('First Name')),
            'last_name': self._clean(raw_row.get('Last Name')),
            'linkedin_url': self._clean(raw_row.get('LinkedIn URL')),
            'recipient_email': self._clean(raw_row.get('Recipient')),
            'title': self._clean(raw_row.get('Title')),
            'city': self._clean(raw_row.get('City')),
            'subject': self._clean(raw_row.get('Subject')),
            'campaign_name': self._clean(raw_row.get('Campaign Name')),
            'num_opens': opens,
            'num_clicks': self._parse_int(raw_row.get('Clicks')),
            'replied': self._parse_bool(raw_row.get('Replied?')),
            'status': self._clean(raw_row.get('Status')),
            'email_status': self._clean(raw_row.get('Email Status')),
            'sent_at': self._parse_datetime(raw_row.get('Sent At')),
            'last_opened_at': self._parse_datetime(raw_row.get('Last Opened')),
            'lead_category': self._clean(raw_row.get('Lead Category')) or self._categorize_lead(opens),
        }

    def _flush_batch(self, batch_rows, batch_campaign_payloads, campaign_cache, stats, fetch_existing):
        self._upsert_campaigns(batch_campaign_payloads, campaign_cache, stats, fetch_existing=fetch_existing)
        self._upsert_messages(batch_rows, campaign_cache, stats, fetch_existing=fetch_existing)

    def _upsert_campaigns(self, campaign_payloads, campaign_cache, stats, fetch_existing):
        if not campaign_payloads:
            return

        campaign_ids = [campaign_id for campaign_id in campaign_payloads if campaign_id not in campaign_cache]
        if not campaign_ids:
            return

        existing_campaigns = (
            ApolloCampaign.objects.in_bulk(campaign_ids, field_name='apollo_id')
            if fetch_existing else {}
        )
        now = timezone.now()
        campaigns_to_create = []
        campaigns_to_update = []

        for campaign_id in campaign_ids:
            payload = campaign_payloads[campaign_id]
            existing = existing_campaigns.get(campaign_id)
            if existing is None:
                campaigns_to_create.append(
                    ApolloCampaign(
                        apollo_id=campaign_id,
                        name=payload['name'],
                        raw_data=payload['raw_data'],
                        last_synced_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                stats['campaigns_created'] += 1
                continue

            existing.name = payload['name']
            existing.raw_data = payload['raw_data']
            existing.last_synced_at = now
            existing.updated_at = now
            campaigns_to_update.append(existing)
            stats['campaigns_updated'] += 1

        if campaigns_to_create:
            ApolloCampaign.objects.bulk_create(campaigns_to_create, batch_size=500)
        if campaigns_to_update:
            ApolloCampaign.objects.bulk_update(
                campaigns_to_update,
                ['name', 'raw_data', 'last_synced_at', 'updated_at'],
                batch_size=500,
            )
        campaign_cache.update(ApolloCampaign.objects.in_bulk(campaign_ids, field_name='apollo_id'))

    def _upsert_messages(self, rows, campaign_cache, stats, fetch_existing):
        if not rows:
            return

        deduped_rows = {}
        for row_data in rows:
            message_id = row_data['normalized']['message_id']
            if message_id in deduped_rows:
                stats['duplicate_rows'] += 1
            deduped_rows[message_id] = row_data

        message_ids = list(deduped_rows.keys())
        existing_messages = (
            ApolloMessage.objects.in_bulk(message_ids, field_name='apollo_id')
            if fetch_existing else {}
        )
        now = timezone.now()
        messages_to_create = []
        messages_to_update = []

        for row_data in deduped_rows.values():
            row = row_data['normalized']
            raw_row = row_data['raw_row']
            campaign = campaign_cache.get(row_data['campaign_id']) if row_data['campaign_id'] else None
            existing = existing_messages.get(row['message_id'])
            payload = {
                'campaign': campaign,
                'recipient_email': row['recipient_email'],
                'first_name': row['first_name'],
                'last_name': row['last_name'],
                'linkedin_url': row['linkedin_url'],
                'title': row['title'],
                'city': row['city'],
                'subject': row['subject'],
                'num_opens': row['num_opens'],
                'num_clicks': row['num_clicks'],
                'replied': row['replied'],
                'status': row['status'],
                'email_status': row['email_status'],
                'sent_at': row['sent_at'],
                'last_opened_at': row['last_opened_at'],
                'lead_category': row['lead_category'],
                'raw_message': {
                    'source': 'csv',
                    'row': raw_row,
                },
                'raw_activity': {},
                'last_synced_at': now,
                'updated_at': now,
            }

            if existing is None:
                messages_to_create.append(
                    ApolloMessage(
                        apollo_id=row['message_id'],
                        created_at=now,
                        **payload,
                    )
                )
                stats['messages_created'] += 1
                continue

            for field, value in payload.items():
                setattr(existing, field, value)
            messages_to_update.append(existing)
            stats['messages_updated'] += 1

        if messages_to_create:
            ApolloMessage.objects.bulk_create(messages_to_create, batch_size=500)
        if messages_to_update:
            ApolloMessage.objects.bulk_update(
                messages_to_update,
                [
                    'campaign',
                    'recipient_email',
                    'first_name',
                    'last_name',
                    'linkedin_url',
                    'title',
                    'city',
                    'subject',
                    'num_opens',
                    'num_clicks',
                    'replied',
                    'status',
                    'email_status',
                    'sent_at',
                    'last_opened_at',
                    'lead_category',
                    'raw_message',
                    'raw_activity',
                    'last_synced_at',
                    'updated_at',
                ],
                batch_size=500,
            )

    def _clean(self, value):
        if value is None:
            return ''
        cleaned = str(value).strip()
        if cleaned in {'', 'N/A', 'n/a', 'NA', 'na', 'None', 'none', '-'}:
            return ''
        return cleaned

    def _parse_int(self, value):
        cleaned = self._clean(value)
        if not cleaned:
            return 0
        try:
            return int(float(cleaned))
        except ValueError as exc:
            raise CommandError(f'Invalid integer value in CSV: {value}') from exc

    def _parse_bool(self, value):
        cleaned = self._clean(value).lower()
        return cleaned in {'yes', 'true', '1', 'replied'}

    def _parse_datetime(self, value):
        cleaned = self._clean(value)
        if not cleaned:
            return None
        for date_format in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y'):
            try:
                parsed = datetime.strptime(cleaned, date_format)
                return timezone.make_aware(parsed, timezone.get_current_timezone())
            except ValueError:
                continue
        raise CommandError(f'Unsupported datetime format in CSV: {value}')

    def _campaign_key(self, campaign_name):
        digest = sha1(campaign_name.strip().lower().encode('utf-8')).hexdigest()[:20]
        return f'csv:{digest}'

    def _categorize_lead(self, opens):
        if opens >= 3:
            return 'WARM'
        if opens == 2:
            return 'Engaged'
        return 'Cold'
