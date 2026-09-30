import pytest

from App import app, db, User


@pytest.fixture
def client():
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite://")
    with app.app_context():
        db.drop_all()
        db.create_all()
    with app.test_client() as client:
        yield client
    with app.app_context():
        db.drop_all()


def test_registration_works_without_otp_verification(client):
    response = client.post(
        "/register",
        data={
            "full_name": "Adaeze Okafor",
            "matric": "U21CS1042",
            "email": "adaeze@tech-u.edu.ng",
            "faculty": "Science",
            "department": "Computer Science",
            "programme": "B.Sc. Computer Science",
            "password": "StrongPass123",
            "confirm_pw": "StrongPass123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"

    with app.app_context():
        user = User.query.filter_by(matric="U21CS1042").first()
        assert user is not None
        assert user.email == "adaeze@tech-u.edu.ng"


def test_unnecessary_auth_routes_are_removed(client):
    assert client.get("/forgot-password").status_code == 404
    assert client.get("/verify-otp").status_code == 404
    assert client.get("/resend-otp").status_code == 404
