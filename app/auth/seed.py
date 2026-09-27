from flask import Blueprint, current_app, jsonify

from app.auth import cognito_client
from app.auth.cognito_client import UsernameExistsError

seed_bp = Blueprint("seed", __name__)


def _delete_existing_admin() -> None:
    # Cascades likes/progress too (not just group membership) so
    # re-seeding doesn't leave orphaned DynamoDB rows behind.
    from app.auth.routes import _delete_user_data

    _delete_user_data("admin")


@seed_bp.route("/seed-users", methods=["POST"])
def seed_users():
    """Dev-only convenience endpoint that seeds demo accounts.

    Unauthenticated by design (mirrors the reference app) so a fresh
    deployment can be bootstrapped right after `terraform apply`. Gated
    by SEED_USERS_ENABLED so it can be disabled outright for any
    production-facing deployment.
    """
    if not current_app.config.get("SEED_USERS_ENABLED"):
        return jsonify({"error": "not found"}), 404

    try:
        cognito_client.register("admin", "admin@quote-app.local", "Admin123!")
    except UsernameExistsError:
        _delete_existing_admin()
        cognito_client.register("admin", "admin@quote-app.local", "Admin123!")
    cognito_client.add_user_to_group("admin", "ADMIN")

    try:
        cognito_client.register("user-1", "user-1@outlook.com", "Hello-user-1")
    except UsernameExistsError:
        pass  # already seeded, matches the source's idempotent-for-user-1 behavior

    return jsonify({"message": "Users seeded successfully"}), 200
