from flask import Blueprint, current_app, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz", methods=["GET"])
def healthz():
    try:
        from app.aws_clients import dynamodb_resource

        table = dynamodb_resource().Table(current_app.config["QUOTES_TABLE"])
        table.get_item(Key={"id": 0})
        return jsonify({"status": "ok"}), 200
    except Exception as exc:
        return jsonify({"status": "error", "detail": str(exc)}), 503
