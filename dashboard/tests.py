"""Tests for the US07a staff dashboard – metrics and availability calculations."""

from unittest.mock import patch
from django.http import request
from django.test import RequestFactory
from dashboard.views import index
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from unittest.mock import patch as mock_patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from dashboard.views import get_staff_api_token

class TestDashboardMetrics:
    """Verify request metric counts are calculated correctly from API data."""

    def setup_method(self):
        self.factory = RequestFactory()

    @patch("dashboard.views._get_json")
    def test_total_requests_count(self, mock_get):
        mock_get.return_value = [
            {"id": 1, "status": "new", "description": "a"},
            {"id": 2, "status": "in progress", "description": "b"},
            {"id": 3, "status": "completed", "description": "c"},
        ]
        request = self.factory.get("/")
        request.user = Mock()
        request.user.groups.filter.return_value.exists.return_value = True

        response = index.__wrapped__(request)

        assert response.status_code == 200
        # Context is not directly accessible from HttpResponse; check content instead.
        assert b"3" in response.content  # total_requests = 3

    @patch("dashboard.views._get_json")
    def test_outstanding_and_completed_counts(self, mock_get):
        """Outstanding = new + in progress; completed is separate."""
        mock_get.return_value = [
            {"id": 1, "status": "new"},
            {"id": 2, "status": "in progress"},
            {"id": 3, "status": "completed"},
            {"id": 4, "status": "new"},
        ]

        request = self.factory.get("/")
        request.user = Mock()
        request.user.groups.filter.return_value.exists.return_value = True

        response = index.__wrapped__(request)

        assert response.status_code == 200
        # 2 new + 1 in progress = 3 outstanding; 1 completed
        assert b">3<" in response.content   # outstanding_count
        assert b">1<" in response.content   # completed_count


class TestDashboardCentres:
    """Verify cooling-centre availability and utilisation calculations."""

    def setup_method(self):
        self.factory = RequestFactory()

    @patch("dashboard.views._get_json")
    def test_centre_availability_reflects_bookings(self, mock_get):
        """A centre with bookings should show reduced spaces_available."""
        mock_get.return_value = [
            {
                "id": 1,
                "name": "Test Centre",
                "area": "Test Area",
                "capacity": 10,
                "spaces_available": 7,
                "opening_hours": "09:00-17:00",
                "status": "open",
            }
        ]


        request = self.factory.get("/")
        request.user = Mock()
        request.user.groups.filter.return_value.exists.return_value = True

        response = index.__wrapped__(request)

        assert response.status_code == 200
        # 3 spaces used out of 10 → 30% utilisation
        assert b"30.0%" in response.content
        assert b">7<" in response.content   # spaces_available

    @patch("dashboard.views._get_json")
    def test_full_capacity_zero_utilisation(self, mock_get):
        """A centre with no bookings should show 0% utilisation."""
        mock_get.return_value = [
            {
                "id": 1,
                "name": "Full Centre",
                "area": "Test Area",
                "capacity": 20,
                "spaces_available": 20,
                "opening_hours": "",
                "status": "open",
            }
        ]


        request = self.factory.get("/")
        request.user = Mock()
        request.user.groups.filter.return_value.exists.return_value = True

        response = index.__wrapped__(request)

        assert response.status_code == 200
        assert b"0.0%" in response.content   # utilisation
        assert b">20<" in response.content   # spaces_available == capacity

    @patch("dashboard.views._get_json")
    def test_overall_utilisation_calculation(self, mock_get):
        """Overall utilisation should be computed across all centres."""
        mock_get.return_value = [
            {"id": 1, "name": "A", "area": "X", "capacity": 10, "spaces_available": 5},
            {"id": 2, "name": "B", "area": "Y", "capacity": 10, "spaces_available": 8},
        ]


        request = self.factory.get("/")
        request.user = Mock()
        request.user.groups.filter.return_value.exists.return_value = True

        response = index.__wrapped__(request)

        assert response.status_code == 200
        # Total capacity: 20, total available: 13 → used: 7 → 35%
        assert b"35.0%" in response.content

    @patch("dashboard.views._get_json")
    def test_empty_centres_list(self, mock_get):
        """When no centres exist, totals should be zero."""
        mock_get.return_value = []


        request = self.factory.get("/")
        request.user = Mock()
        request.user.groups.filter.return_value.exists.return_value = True

        response = index.__wrapped__(request)

        assert response.status_code == 200
        # Check that "No centres found." message appears
        assert b"No centres found." in response.content


class TestDashboardApiErrorHandling:
    """Verify graceful handling when Flask API is unreachable."""

    def setup_method(self):
        self.factory = RequestFactory()

    @patch("dashboard.views._get_json")
    def test_empty_data_on_api_failure(self, mock_get):
        """When the API fails, dashboard should render with empty data."""
        mock_get.return_value = []


        request = self.factory.get("/")
        request.user = Mock()
        request.user.groups.filter.return_value.exists.return_value = True

        response = index.__wrapped__(request)

        assert response.status_code == 200
        # Check that "No requests found." message appears
        assert b"No requests found." in response.content
        assert b"No centres found." in response.content

class US07cRequestDetailTests(TestCase):
    """Automated access-control and request-detail tests."""

    def setUp(self):
        self.url = reverse(
            "dashboard:request_detail",
            kwargs={"request_id": 1},
        )

        self.user = get_user_model().objects.create_user(
            username="us07c_staff",
            password="TestPassword123!",
        )

        self.group = Group.objects.create(
            name="Heat Shield Staff"
        )

        self.sample_request = {
            "id": 1,
            "description": "Test welfare request",
            "category": "welfare",
            "area": "Bolton",
            "priority": "medium",
            "status": "new",
            "created_at": "2026-11-26 10:00:00",
            "updated_at": "2026-11-26 10:00:00",
        }

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_authenticated_user_without_staff_group_forbidden(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    @patch("dashboard.views._get_json")
    def test_authorised_staff_can_view_request(self, mock_get):
        self.user.groups.add(self.group)
        self.client.force_login(self.user)
        mock_get.return_value = self.sample_request

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test welfare request")
        self.assertContains(response, "Bolton")
        self.assertContains(response, "New")

    @patch("dashboard.views._get_json")
    def test_missing_request_returns_404(self, mock_get):
        self.user.groups.add(self.group)
        self.client.force_login(self.user)
        mock_get.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    @patch("dashboard.views._get_json")
    @patch("dashboard.views.update_request_status")
    def test_valid_status_update_redirects(
        self, mock_update, mock_get
    ):
        self.user.groups.add(self.group)
        self.client.force_login(self.user)

        mock_update.return_value = (
            True,
            "Request status updated successfully.",
        )

        response = self.client.post(
            self.url,
            {"status": "in progress"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.url)

        mock_update.assert_called_once_with(
            self.user,
            1,
            "in progress",
        )

    @patch("dashboard.views._get_json")
    @patch("dashboard.views.update_request_status")
    def test_invalid_status_displays_error(
        self, mock_update, mock_get
    ):
        self.user.groups.add(self.group)
        self.client.force_login(self.user)

        mock_update.return_value = (
            False,
            "Invalid request status.",
        )
        mock_get.return_value = self.sample_request

        response = self.client.post(
            self.url,
            {"status": "invalid"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Invalid request status.",
        )

    @patch("dashboard.views.update_request_status")
    def test_unauthorised_user_cannot_update(
        self, mock_update
    ):
        self.client.force_login(self.user)

        response = self.client.post(
            self.url,
            {"status": "completed"},
        )

        self.assertEqual(response.status_code, 403)
        mock_update.assert_not_called()


    @patch("dashboard.views.update_request_status")
    def test_status_update_requires_csrf_token(self, mock_update):
        """Reject status updates without a valid CSRF token."""

        self.user.groups.add(self.group)

        csrf_client = self.client_class(
            enforce_csrf_checks=True
        )
        csrf_client.force_login(self.user)

        response = csrf_client.post(
            self.url,
            {"status": "completed"},
        )

        self.assertEqual(response.status_code, 403)
        mock_update.assert_not_called()


    def test_anonymous_user_cannot_access_dashboard(self):
        """Anonymous visitors must be redirected to login."""
        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_unauthorised_user_cannot_access_dashboard(self):
        """Signed-in users without staff permission must be rejected."""
        self.client.force_login(self.user)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 403)

    @patch("dashboard.views._get_json")
    def test_authorised_staff_can_access_dashboard(self, mock_get):
        """Authorised staff must be able to access the dashboard."""
        self.user.groups.add(self.group)
        self.client.force_login(self.user)

        mock_get.return_value = []

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)


class US07cAPIIntegrationTests(TestCase):
    """Verify the Django-to-Flask status-update integration."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="heatshield_staff",
            password="TestPassword123!",
        )
        group = Group.objects.create(name="Heat Shield Staff")
        self.user.groups.add(group)

    @patch("dashboard.views.requests.patch")
    @patch("dashboard.views.get_staff_api_token")
    def test_valid_update_calls_authenticated_flask_api(
        self, mock_token, mock_patch
    ):
        mock_token.return_value = "test-token-only"
        mock_patch.return_value.status_code = 200

        from dashboard.views import update_request_status

        success, message = update_request_status(
            self.user, 1, "completed"
        )

        self.assertTrue(success)
        self.assertEqual(
            message,
            "Request status updated successfully.",
        )

        mock_patch.assert_called_once()

        arguments = mock_patch.call_args
        self.assertTrue(
            arguments.args[0].endswith("/requests/1")
        )
        self.assertEqual(
            arguments.kwargs["json"],
            {"status": "completed"},
        )
        self.assertEqual(
            arguments.kwargs["headers"]["Authorization"],
            "Bearer test-token-only",
        )

    @patch("dashboard.views.requests.patch")
    def test_invalid_status_never_reaches_flask(self, mock_patch):
        from dashboard.views import update_request_status

        success, message = update_request_status(
            self.user, 1, "invalid-status"
        )

        self.assertFalse(success)
        self.assertEqual(message, "Invalid request status.")
        mock_patch.assert_not_called()

    @patch("dashboard.views.requests.patch")
    @patch("dashboard.views.get_staff_api_token")
    def test_flask_rejects_unauthorised_update(
        self, mock_token, mock_patch
    ):
        mock_token.return_value = "test-token-only"
        mock_patch.return_value.status_code = 403

        from dashboard.views import update_request_status

        success, message = update_request_status(
            self.user, 1, "completed"
        )

        self.assertFalse(success)
        self.assertIn("not authorised", message)


class US07cAPIIntegrationTests(TestCase):
    """Verify the Django-to-Flask status-update integration."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="heatshield_staff",
            password="TestPassword123!",
        )
        group = Group.objects.create(name="Heat Shield Staff")
        self.user.groups.add(group)

    @patch("dashboard.views.requests.patch")
    @patch("dashboard.views.get_staff_api_token")
    def test_valid_update_calls_authenticated_flask_api(
        self, mock_token, mock_patch
    ):
        mock_token.return_value = "test-token-only"
        mock_patch.return_value.status_code = 200

        from dashboard.views import update_request_status

        success, message = update_request_status(
            self.user, 1, "completed"
        )

        self.assertTrue(success)
        self.assertEqual(
            message,
            "Request status updated successfully.",
        )

        mock_patch.assert_called_once()

        arguments = mock_patch.call_args
        self.assertTrue(
            arguments.args[0].endswith("/requests/1")
        )
        self.assertEqual(
            arguments.kwargs["json"],
            {"status": "completed"},
        )
        self.assertEqual(
            arguments.kwargs["headers"]["Authorization"],
            "Bearer test-token-only",
        )

    @patch("dashboard.views.requests.patch")
    def test_invalid_status_never_reaches_flask(self, mock_patch):
        from dashboard.views import update_request_status

        success, message = update_request_status(
            self.user, 1, "invalid-status"
        )

        self.assertFalse(success)
        self.assertEqual(message, "Invalid request status.")
        mock_patch.assert_not_called()

    @patch("dashboard.views.requests.patch")
    @patch("dashboard.views.get_staff_api_token")
    def test_flask_rejects_unauthorised_update(
        self, mock_token, mock_patch
    ):
        mock_token.return_value = "test-token-only"
        mock_patch.return_value.status_code = 403

        from dashboard.views import update_request_status

        success, message = update_request_status(
            self.user, 1, "completed"
        )

        self.assertFalse(success)
        self.assertIn("not authorised", message)

class US07cCredentialSecurityTests(TestCase):
    """Verify staff API credential resolution and access restrictions."""

    def setUp(self):
        self.group = Group.objects.create(name="Heat Shield Staff")
        self.user = get_user_model().objects.create_user(
            username="test_staff",
            password="TestPassword123!"
        )
        self.user.groups.add(self.group)

    @mock_patch.dict(
        "os.environ",
        {"HEATSHIELD_API_TOKEN_TEST_STAFF": "test-token"},
    )
    def test_authorised_staff_token_is_available(self):
        self.assertEqual(
            get_staff_api_token(self.user),
            "test-token"
        )

    def test_unauthorised_user_cannot_retrieve_token(self):
        self.user.groups.remove(self.group)

        self.assertIsNone(get_staff_api_token(self.user))

    def test_inactive_user_cannot_retrieve_token(self):
        self.user.is_active = False

        self.assertIsNone(get_staff_api_token(self.user))

    def test_invalid_username_cannot_resolve_token(self):
        self.user.username = "../invalid"

        self.assertIsNone(get_staff_api_token(self.user))

    def test_missing_environment_token_is_rejected(self):
        with mock_patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(get_staff_api_token(self.user))
