"""Model configuration for the my-agent customer support agent.

Defaults to Amazon Nova Micro in ca-central-1 via the Canada regional
inference profile, keeping inference inside Canada.

Override without editing code:
    export MODEL_ID=ca.amazon.nova-micro-v1:0
    export AWS_REGION=ca-central-1
"""

import os

import boto3
from strands.models import BedrockModel

MODEL_ID = os.environ.get("MODEL_ID", "ca.amazon.nova-micro-v1:0")
REGION = os.environ.get("AWS_REGION", "ca-central-1")


def load_model() -> BedrockModel:
    """Build the Strands Bedrock model for Nova Micro in ca-central-1."""
    session = boto3.Session(region_name=REGION)
    return BedrockModel(
        model_id=MODEL_ID,
        boto_session=session,
    )
