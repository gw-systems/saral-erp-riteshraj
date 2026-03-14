"""
Gmail Advanced Search Service
Gmail-style search with operators
"""

import re
from datetime import datetime
from django.db.models import Q
from gmail.models import Thread, Message
import logging

logger = logging.getLogger("gmail.search")


class SearchService:
    """Gmail-style advanced search with operators"""

    @staticmethod
    def parse_query(query_string):
        """
        Parse Gmail-style search query

        Supported operators:
        - from:email@example.com
        - to:email@example.com
        - subject:keyword
        - has:attachment
        - is:unread, is:starred, is:important
        - after:2024/01/01
        - before:2024/12/31
        - filename:report.pdf
        """
        filters = {
            'from_email': None,
            'to_email': None,
            'subject': None,
            'has_attachment': False,
            'is_unread': False,
            'is_starred': False,
            'after_date': None,
            'before_date': None,
            'filename': None,
            'text_search': []
        }

        # Extract operators
        operators = {
            'from': r'from:(\S+)',
            'to': r'to:(\S+)',
            'subject': r'subject:(\S+)',
            'has': r'has:(\S+)',
            'is': r'is:(\S+)',
            'after': r'after:(\d{4}/\d{2}/\d{2})',
            'before': r'before:(\d{4}/\d{2}/\d{2})',
            'filename': r'filename:(\S+)'
        }

        for operator, pattern in operators.items():
            matches = re.findall(pattern, query_string)
            for match in matches:
                if operator == 'from':
                    filters['from_email'] = match
                elif operator == 'to':
                    filters['to_email'] = match
                elif operator == 'subject':
                    filters['subject'] = match
                elif operator == 'has' and match == 'attachment':
                    filters['has_attachment'] = True
                elif operator == 'is':
                    if match == 'unread':
                        filters['is_unread'] = True
                    elif match == 'starred':
                        filters['is_starred'] = True
                elif operator == 'after':
                    try:
                        filters['after_date'] = datetime.strptime(match, '%Y/%m/%d')
                    except:
                        pass
                elif operator == 'before':
                    try:
                        filters['before_date'] = datetime.strptime(match, '%Y/%m/%d')
                    except:
                        pass
                elif operator == 'filename':
                    filters['filename'] = match

        # Remove operators from query to get text search terms
        for pattern in operators.values():
            query_string = re.sub(pattern, '', query_string)

        # Remaining text is full-text search
        filters['text_search'] = query_string.strip().split()

        return filters

    @staticmethod
    def execute_search(user, query_string):
        """
        Execute search and return matching threads

        Args:
            user: User performing search
            query_string: Search query with operators

        Returns:
            QuerySet of Thread objects
        """
        try:
            filters = SearchService.parse_query(query_string)

            # Build QuerySet - start with user's accessible threads
            queryset = Thread.get_threads_for_user(user)

            # Apply filters
            if filters['from_email']:
                queryset = queryset.filter(
                    messages__from_contact__email__icontains=filters['from_email']
                )

            if filters['to_email']:
                queryset = queryset.filter(
                    messages__to_contacts__email__icontains=filters['to_email']
                )

            if filters['subject']:
                queryset = queryset.filter(subject__icontains=filters['subject'])

            if filters['has_attachment']:
                queryset = queryset.filter(messages__has_attachments=True)

            if filters['is_unread']:
                queryset = queryset.filter(has_unread=True)

            if filters['is_starred']:
                queryset = queryset.filter(is_starred=True)

            if filters['after_date']:
                queryset = queryset.filter(last_message_date__gte=filters['after_date'])

            if filters['before_date']:
                queryset = queryset.filter(last_message_date__lte=filters['before_date'])

            if filters['filename']:
                queryset = queryset.filter(
                    messages__attachments_meta__contains=[{'filename': filters['filename']}]
                )

            # Full-text search on subject, snippet, body
            if filters['text_search']:
                q_objects = Q()
                for term in filters['text_search']:
                    q_objects |= Q(subject__icontains=term)
                    q_objects |= Q(snippet__icontains=term)
                    q_objects |= Q(messages__body_text__icontains=term)
                    q_objects |= Q(messages__body_html__icontains=term)
                queryset = queryset.filter(q_objects)

            # Return distinct threads ordered by date
            return queryset.distinct().order_by('-last_message_date')

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return Thread.objects.none()
