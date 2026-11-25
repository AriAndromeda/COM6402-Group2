"""Tests for the US07a staff dashboard – metrics and availability calculations."""

from unittest.mock import patch

from django.test import RequestFactory

from dashboard.views import index


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
        response = index(request)

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
        response = index(request)

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
        response = index(request)

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
        response = index(request)

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
        response = index(request)

        assert response.status_code == 200
        # Total capacity: 20, total available: 13 → used: 7 → 35%
        assert b"35.0%" in response.content

    @patch("dashboard.views._get_json")
    def test_empty_centres_list(self, mock_get):
        """When no centres exist, totals should be zero."""
        mock_get.return_value = []

        request = self.factory.get("/")
        response = index(request)

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
        response = index(request)

        assert response.status_code == 200
        # Check that "No requests found." message appears
        assert b"No requests found." in response.content
        assert b"No centres found." in response.content


class TestUs07bSearchableQueue:
    """US07b: search and filter support requests on the dashboard."""

    def setup_method(self):
        self.factory = RequestFactory()
        self.sample_requests = [
            {
                "id": 1,
                "description": "Urgent water assistance",
                "category": "welfare",
                "area": "Bolton",
                "priority": "high",
                "status": "new",
            },
            {
                "id": 2,
                "description": "Cooling centre place needed",
                "category": "cooling",
                "area": "Manchester",
                "priority": "low",
                "status": "in progress",
            },
            {
                "id": 3,
                "description": "General welfare check",
                "category": "welfare",
                "area": "Bolton",
                "priority": "medium",
                "status": "completed",
            },
        ]

    @patch("dashboard.views._get_json")
    def test_filter_form_is_shown(self, mock_get):
        mock_get.return_value = []
        response = index(self.factory.get("/"))
        assert response.status_code == 200
        assert b'name="status"' in response.content
        assert b'name="priority"' in response.content
        assert b'name="area"' in response.content
        assert b'name="q"' in response.content

    @patch("dashboard.views._get_json")
    def test_status_priority_area_filters_call_flask_api(self, mock_get):
        """Filters are forwarded to GET /api/requests as query params."""
        mock_get.return_value = [self.sample_requests[0]]

        request = self.factory.get(
            "/",
            data={
                "status": "new",
                "priority": "high",
                "area": "Bolton",
            },
        )
        response = index(request)

        assert response.status_code == 200
        # Metrics use unfiltered /requests; queue uses filtered path.
        paths = [call.args[0] for call in mock_get.call_args_list]
        assert "/requests" in paths
        filtered = [p for p in paths if "?" in p]
        assert filtered, "expected a filtered /requests API call"
        assert "status=new" in filtered[0]
        assert "priority=high" in filtered[0]
        assert "area=Bolton" in filtered[0]
        assert b"Urgent water assistance" in response.content

    @patch("dashboard.views._get_json")
    def test_combined_filters_and_search_match_results(self, mock_get):
        mock_get.side_effect = [
            self.sample_requests,  # metrics (unfiltered)
            [self.sample_requests[0], self.sample_requests[2]],  # filtered queue
            [],  # centres
        ]

        request = self.factory.get(
            "/",
            data={"status": "new", "area": "bolton", "q": "water"},
        )
        response = index(request)

        assert response.status_code == 200
        assert b"Urgent water assistance" in response.content
        assert b"General welfare check" not in response.content
        assert b"Cooling centre place needed" not in response.content

    @patch("dashboard.views._get_json")
    def test_no_matching_results_shows_clear_message(self, mock_get):
        mock_get.side_effect = [
            self.sample_requests,
            [],  # filtered queue empty
            [],  # centres
        ]

        request = self.factory.get("/", data={"status": "completed", "area": "Liverpool"})
        response = index(request)

        assert response.status_code == 200
        assert b"No requests match your search." in response.content
