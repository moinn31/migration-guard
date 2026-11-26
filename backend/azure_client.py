import logging
import ipaddress
from urllib.parse import urlparse
from typing import Optional
from azure.identity import DefaultAzureCredential
from azure.mgmt.appcontainers import ContainerAppsAPIClient
from azure.mgmt.appcontainers.models import (
    JobExecutionTemplate,
    JobExecutionContainer,
    EnvironmentVar,
)
from .config import settings

logger = logging.getLogger(__name__)

class AzureJobService:
    def __init__(self):
        self.subscription_id = settings.azure_subscription_id
        self.resource_group = settings.azure_resource_group
        self.job_name = settings.azure_containerapps_job_name
        self._client: Optional[ContainerAppsAPIClient] = None

    def get_client(self) -> ContainerAppsAPIClient:
        if self._client is None:
            credential = DefaultAzureCredential()
            self._client = ContainerAppsAPIClient(credential, self.subscription_id)
        return self._client

    def trigger_job(self, job_id: str, backend_url: str, job_token: str) -> Optional[str]:
        """
        Triggers execution of the Azure Container Apps Job 'migration-worker'
        passing only the job_id, backend_url, and short-lived job_token.
        """
        if not settings.azure_enabled:
            logger.info("Azure integration disabled by configuration.")
            return None

        parsed = urlparse(backend_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.hostname.lower() == 'localhost':
            raise ValueError('Azure requires BACKEND_PUBLIC_URL with a public HTTPS address')
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise ValueError('Azure callback cannot use a local or private IP address')

        try:
            client = self.get_client()
            logger.info(f"Triggering Azure Container Apps Job '{self.job_name}' for job_id={job_id}")

            template = JobExecutionTemplate(
                containers=[
                    JobExecutionContainer(
                        name="migration-worker",
                        env=[
                            EnvironmentVar(name="JOB_ID", value=job_id),
                            EnvironmentVar(name="BACKEND_URL", value=backend_url),
                            EnvironmentVar(name="JOB_TOKEN", value=job_token),
                        ]
                    )
                ]
            )

            poller = client.jobs.begin_start(
                resource_group_name=self.resource_group,
                job_name=self.job_name,
                template=template,
            )
            execution = poller.result()
            execution_id = getattr(execution, "name", None) or getattr(execution, "id", None) or "started"
            logger.info(f"Azure Job started successfully with execution_id: {execution_id}")
            return str(execution_id)

        except Exception as e:
            logger.warning(f"Could not trigger Azure Container Apps Job directly: {e}")
            return None

azure_job_service = AzureJobService()
