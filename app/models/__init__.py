# Import every model so Base.metadata knows all tables.
from app.models import activity, case, diagnosis, disease_report, location, user  # noqa: F401
