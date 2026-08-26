"""Construction and tenant-scoping checks for the simpler entities.

Task has real behaviour (a state machine) and gets its own file: test_task.py.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.entities.organization import Organization
from revops.domain.entities.user import User
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress


def test_organization_defaults_to_demo_mode() -> None:
    org = Organization(id=uuid4(), name="Acme Inc")
    assert org.demo_mode is True


def test_user_is_scoped_to_its_organization() -> None:
    org_id = uuid4()
    user = User(id=uuid4(), organization_id=org_id, email=EmailAddress("a@b.com"), role="rep")
    assert user.organization_id == org_id


def test_account_holds_a_normalized_domain() -> None:
    account = Account(
        id=uuid4(),
        organization_id=uuid4(),
        company_name="Acme Inc",
        domain=CompanyDomain("https://www.acme.com"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert account.domain.value == "acme.com"


def test_contact_belongs_to_one_account() -> None:
    account_id = uuid4()
    contact = Contact(
        id=uuid4(),
        organization_id=uuid4(),
        account_id=account_id,
        email=EmailAddress("jane@acme.com"),
        full_name="Jane Doe",
    )
    assert contact.account_id == account_id
    assert contact.title == ""  # optional field defaults sensibly


def test_interaction_belongs_to_one_account() -> None:
    account_id = uuid4()
    interaction = Interaction(
        id=uuid4(),
        organization_id=uuid4(),
        account_id=account_id,
        channel="email",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert interaction.account_id == account_id


def test_open_opportunity_stages_are_open() -> None:
    for stage in (
        OpportunityStage.PROSPECTING,
        OpportunityStage.QUALIFICATION,
        OpportunityStage.PROPOSAL,
        OpportunityStage.NEGOTIATION,
    ):
        opp = Opportunity(
            id=uuid4(),
            organization_id=uuid4(),
            account_id=uuid4(),
            stage=stage,
            value=Decimal(1000),
        )
        assert opp.stage.is_open is True


def test_closed_opportunity_stages_are_not_open() -> None:
    for stage in (OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST):
        opp = Opportunity(
            id=uuid4(),
            organization_id=uuid4(),
            account_id=uuid4(),
            stage=stage,
            value=Decimal(1000),
        )
        assert opp.stage.is_open is False
