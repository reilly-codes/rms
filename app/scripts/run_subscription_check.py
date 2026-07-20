"""
Run the subscription billing check once and exit.

Mirrors how the ONA24 expire_subscriptions cron is wired: a plain script,
invoked daily by a systemd timer / cron entry, not an HTTP endpoint. e.g.

    */30 * * * *  cd /home/mellow/projects/rms && \
        /home/mellow/projects/rms/venv/bin/python -m app.scripts.run_subscription_check \
        >> /var/log/rms-subscription-check.log 2>&1

Run from the project root so `app` resolves as a package:
    python -m app.scripts.run_subscription_check
"""
import logging
from sqlmodel import Session

from app.core.database import engine
from app.services.subscription_service import SubscriptionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("subscription_check")


def main():
    with Session(engine) as session:
        result = SubscriptionService.run_subscription_billing_check(session)
        logger.info(
            "Subscription check complete: checked=%s grace=%s suspended=%s deleted=%s",
            result["checked"], result["moved_to_grace"], result["moved_to_suspended"], result["deleted_accounts"],
        )


if __name__ == "__main__":
    main()
