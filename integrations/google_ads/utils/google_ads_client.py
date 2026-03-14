"""
Google Ads API Client
Handles communication with Google Ads API v19
"""
import logging

from google.ads.googleads.client import GoogleAdsClient as GAClient
from google.ads.googleads.errors import GoogleAdsException
from django.conf import settings
from .google_ads_auth import GoogleAdsAuth

logger = logging.getLogger(__name__)


class GoogleAdsAPIClient:
    """
    Client for interacting with Google Ads API
    """

    def __init__(self, customer_id, token_data):
        """
        Initialize Google Ads API client

        Args:
            customer_id: Google Ads customer ID (e.g., "3867069282")
            token_data: OAuth2 token data dict
        """
        self.customer_id = customer_id.replace('-', '')  # Remove dashes if present
        self.token_data = token_data
        self.client = None

    def _create_client_config(self):
        """
        Create Google Ads client configuration

        Returns:
            dict: Client configuration
        """
        # Ensure token is valid (refresh if needed)
        self.token_data = GoogleAdsAuth.get_valid_token(self.token_data)

        # client_id/client_secret: prefer what's stored in token_data (set during OAuth flow),
        # fall back to DB settings, then env vars. This ensures client_id matches the refresh_token.
        from integrations.google_ads.utils.settings_helper import get_google_ads_config
        ads_config = get_google_ads_config()
        client_id = (
            self.token_data.get('client_id')
            or ads_config.get('client_id')
            or getattr(settings, 'GOOGLE_ADS_CLIENT_ID', '')
        )
        client_secret = (
            self.token_data.get('client_secret')
            or ads_config.get('client_secret')
            or getattr(settings, 'GOOGLE_ADS_CLIENT_SECRET', '')
        )
        developer_token = (
            ads_config.get('developer_token')
            or getattr(settings, 'GOOGLE_ADS_DEVELOPER_TOKEN', '')
        )

        config = {
            'developer_token': developer_token,
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': self.token_data.get('refresh_token'),
            'login_customer_id': self.customer_id,
            'use_proto_plus': True
        }

        return config

    def get_client(self):
        """
        Get or create Google Ads client

        Returns:
            GoogleAdsClient: Initialized client
        """
        if self.client is None:
            config = self._create_client_config()
            self.client = GAClient.load_from_dict(config)

        return self.client

    def get_campaigns(self):
        """
        Fetch all campaigns for the account

        Returns:
            list: List of campaign dicts
        """
        client = self.get_client()
        ga_service = client.get_service("GoogleAdsService")

        query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign_budget.amount_micros,
                campaign_budget.delivery_method,
                campaign.bidding_strategy_type
            FROM campaign
            WHERE campaign.status != 'REMOVED'
            ORDER BY campaign.name
        """

        try:
            response = ga_service.search(customer_id=self.customer_id, query=query)

            campaigns = []
            for row in response:
                # Calculate daily and monthly budget
                daily_budget_micros = row.campaign_budget.amount_micros if hasattr(row, 'campaign_budget') else None
                daily_budget = daily_budget_micros / 1_000_000 if daily_budget_micros else None

                # Calculate monthly budget (assuming 30.44 days per month on average)
                monthly_budget = daily_budget * 30.44 if daily_budget else None

                campaigns.append({
                    'campaign_id': row.campaign.id,
                    'campaign_name': row.campaign.name,
                    'campaign_status': row.campaign.status.name,
                    'daily_budget': daily_budget,
                    'monthly_budget': monthly_budget,
                    'budget_delivery_method': row.campaign_budget.delivery_method.name if hasattr(row, 'campaign_budget') else None,
                    # Legacy fields (kept for compatibility)
                    'budget_amount': daily_budget,
                    'budget_type': row.campaign_budget.delivery_method.name if hasattr(row, 'campaign_budget') else None,
                    'bidding_strategy': row.campaign.bidding_strategy_type.name,
                    'bidding_strategy_type': row.campaign.bidding_strategy_type.name
                })

            return campaigns

        except GoogleAdsException as ex:
            logger.error(f"Error fetching campaigns: {ex}")
            for error in ex.failure.errors:
                logger.error(f"  Error: {error.message}")
            raise

    def get_campaign_performance(self, start_date, end_date):
        """
        Fetch campaign performance metrics for date range

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            list: List of performance dicts
        """
        client = self.get_client()
        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                segments.date,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.ctr,
                metrics.average_cpc,
                metrics.average_cpm,
                metrics.conversions_from_interactions_rate,
                metrics.cost_per_conversion,
                metrics.search_impression_share
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
                AND campaign.status != 'REMOVED'
            ORDER BY segments.date DESC, campaign.name
        """

        try:
            response = ga_service.search(customer_id=self.customer_id, query=query)

            performance_data = []
            for row in response:
                performance_data.append({
                    'campaign_id': row.campaign.id,
                    'campaign_name': row.campaign.name,
                    'date': row.segments.date,
                    'impressions': row.metrics.impressions,
                    'clicks': row.metrics.clicks,
                    'cost': row.metrics.cost_micros / 1_000_000,
                    'conversions': row.metrics.conversions,
                    'conversion_value': row.metrics.conversions_value,
                    'ctr': row.metrics.ctr,
                    'avg_cpc': row.metrics.average_cpc / 1_000_000 if row.metrics.average_cpc else 0,
                    'avg_cpm': row.metrics.average_cpm / 1_000_000 if row.metrics.average_cpm else 0,
                    'conversion_rate': row.metrics.conversions_from_interactions_rate,
                    'cost_per_conversion': row.metrics.cost_per_conversion / 1_000_000 if row.metrics.cost_per_conversion else 0,
                    'impression_share': row.metrics.search_impression_share if hasattr(row.metrics, 'search_impression_share') else None
                })

            return performance_data

        except GoogleAdsException as ex:
            logger.error(f"Error fetching campaign performance: {ex}")
            for error in ex.failure.errors:
                logger.error(f"  Error: {error.message}")
            raise

    def get_device_performance(self, start_date, end_date):
        """
        Fetch device breakdown performance

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            list: List of device performance dicts
        """
        client = self.get_client()
        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                segments.date,
                segments.device,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions_from_interactions_rate
            FROM campaign
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
                AND campaign.status != 'REMOVED'
            ORDER BY segments.date DESC, segments.device
        """

        try:
            response = ga_service.search(customer_id=self.customer_id, query=query)

            device_data = []
            for row in response:
                device_data.append({
                    'campaign_id': row.campaign.id,
                    'campaign_name': row.campaign.name,
                    'date': row.segments.date,
                    'device': row.segments.device.name,
                    'impressions': row.metrics.impressions,
                    'clicks': row.metrics.clicks,
                    'cost': row.metrics.cost_micros / 1_000_000,
                    'conversions': row.metrics.conversions,
                    'ctr': row.metrics.ctr,
                    'avg_cpc': row.metrics.average_cpc / 1_000_000 if row.metrics.average_cpc else 0,
                    'conversion_rate': row.metrics.conversions_from_interactions_rate
                })

            return device_data

        except GoogleAdsException as ex:
            logger.error(f"Error fetching device performance: {ex}")
            for error in ex.failure.errors:
                logger.error(f"  Error: {error.message}")
            raise

    def get_search_terms(self, start_date, end_date):
        """
        Fetch search terms performance

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            list: List of search term dicts
        """
        client = self.get_client()
        ga_service = client.get_service("GoogleAdsService")

        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                ad_group.id,
                ad_group.name,
                search_term_view.search_term,
                search_term_view.status,
                segments.keyword.info.text,
                segments.keyword.info.match_type,
                segments.search_term_match_type,
                metrics.impressions,
                metrics.clicks,
                metrics.cost_micros,
                metrics.conversions,
                metrics.conversions_value,
                metrics.ctr,
                metrics.average_cpc,
                metrics.conversions_from_interactions_rate,
                metrics.cost_per_conversion
            FROM search_term_view
            WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
                AND campaign.status != 'REMOVED'
            ORDER BY metrics.clicks DESC
        """

        try:
            response = ga_service.search(customer_id=self.customer_id, query=query)

            search_terms = []
            for row in response:
                # Get keyword info from segments (available in search_term_view)
                keyword_text = row.segments.keyword.info.text if hasattr(row.segments, 'keyword') and hasattr(row.segments.keyword, 'info') else None
                keyword_match_type = row.segments.keyword.info.match_type.name if hasattr(row.segments, 'keyword') and hasattr(row.segments.keyword, 'info') else None

                search_terms.append({
                    'campaign_id': row.campaign.id,
                    'campaign_name': row.campaign.name,
                    'ad_group_id': row.ad_group.id,
                    'ad_group_name': row.ad_group.name,
                    'keyword_text': keyword_text,
                    'search_term': row.search_term_view.search_term,
                    'match_type': keyword_match_type or row.segments.search_term_match_type.name,
                    'status': row.search_term_view.status.name,
                    'impressions': row.metrics.impressions,
                    'clicks': row.metrics.clicks,
                    'cost': row.metrics.cost_micros / 1_000_000,
                    'conversions': row.metrics.conversions,
                    'conversion_value': row.metrics.conversions_value,
                    'ctr': row.metrics.ctr,
                    'avg_cpc': row.metrics.average_cpc / 1_000_000 if row.metrics.average_cpc else 0,
                    'conversion_rate': row.metrics.conversions_from_interactions_rate,
                    'cost_per_conversion': row.metrics.cost_per_conversion / 1_000_000 if row.metrics.cost_per_conversion else 0
                })

            return search_terms

        except GoogleAdsException as ex:
            logger.error(f"Error fetching search terms: {ex}")
            for error in ex.failure.errors:
                logger.error(f"  Error: {error.message}")
            raise
