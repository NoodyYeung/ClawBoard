"""
Unit tests for EmailService.

Tests email construction (HTML templates) and send logic with mocked SMTP.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure backend is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.email_service import EmailService


class TestEmailService(unittest.TestCase):
    """Test suite for EmailService."""

    def setUp(self):
        """Set up a test email service with mocked credentials."""
        self.svc = EmailService(
            sender="test@example.com",
            recipients=["recipient1@example.com", "recipient2@example.com"],
            app_password="fake-app-password",
        )

    # ── Initialization Tests ──

    def test_init_with_explicit_params(self):
        """Service initializes with explicit params."""
        self.assertEqual(self.svc.sender, "test@example.com")
        self.assertEqual(self.svc.recipients, ["recipient1@example.com", "recipient2@example.com"])
        self.assertEqual(self.svc.app_password, "fake-app-password")

    @patch.dict(os.environ, {
        "EMAIL_SENDER": "env-sender@test.com",
        "EMAIL_RECIPIENTS": "r1@test.com, r2@test.com",
        "GOOGLE_APP_PASSWORD": "env-pass",
    })
    def test_init_from_env(self):
        """Service picks up config from environment variables."""
        svc = EmailService()
        self.assertEqual(svc.sender, "env-sender@test.com")
        self.assertEqual(svc.recipients, ["r1@test.com", "r2@test.com"])
        self.assertEqual(svc.app_password, "env-pass")

    def test_init_defaults(self):
        """Service uses defaults when no env vars or params."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing env vars
            for key in ["EMAIL_SENDER", "EMAIL_RECIPIENTS", "GOOGLE_APP_PASSWORD"]:
                os.environ.pop(key, None)
            svc = EmailService()
            self.assertEqual(svc.sender, "yeungsys1314@gmail.com")
            self.assertIn("yeungsys1314@gmail.com", svc.recipients)

    # ── HTML Template Tests ──

    def test_pr_html_contains_key_elements(self):
        """PR notification HTML contains task title, PR URL, and project name."""
        html = self.svc._build_pr_html(
            task_title="Fix login bug",
            pr_url="https://github.com/user/repo/pull/42",
            project_name="MyProject",
            dispatch_id=7,
            output_summary="All tests passed",
        )
        self.assertIn("Fix login bug", html)
        self.assertIn("https://github.com/user/repo/pull/42", html)
        self.assertIn("MyProject", html)
        self.assertIn("#7", html)
        self.assertIn("All tests passed", html)
        self.assertIn("Pull Request Ready for Review", html)

    def test_pr_html_without_optional_fields(self):
        """PR HTML works without optional fields (no project, no dispatch, no summary)."""
        html = self.svc._build_pr_html(
            task_title="Add feature",
            pr_url="https://github.com/user/repo/pull/1",
        )
        self.assertIn("Add feature", html)
        self.assertIn("https://github.com/user/repo/pull/1", html)
        # Should NOT contain empty project/dispatch sections
        self.assertNotIn("Project:", html)

    def test_status_html_failed(self):
        """Failed dispatch HTML has correct styling and content."""
        html = self.svc._build_status_html(
            task_title="Deploy service",
            status="failed",
            dispatch_id=12,
            error_reason="Docker build error",
            output_summary="Error: container exited with code 1",
        )
        self.assertIn("Deploy service", html)
        self.assertIn("FAILED", html)
        self.assertIn("❌", html)
        self.assertIn("#12", html)
        self.assertIn("Docker build error", html)
        self.assertIn("container exited with code 1", html)
        self.assertIn("#d32f2f", html)  # red color

    def test_status_html_stopped(self):
        """Stopped dispatch HTML has correct styling."""
        html = self.svc._build_status_html(
            task_title="Run tests",
            status="stopped",
            dispatch_id=5,
        )
        self.assertIn("STOPPED", html)
        self.assertIn("⏸️", html)
        self.assertIn("#f57c00", html)  # orange color

    # ── Send Tests ──

    @patch("services.email_service.smtplib.SMTP")
    def test_send_success(self, mock_smtp_class):
        """Successful send returns True and calls SMTP correctly."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = self.svc.send(
            subject="Test Subject",
            html_body="<p>Hello</p>",
        )

        self.assertTrue(result)
        mock_smtp_class.assert_called_once_with("smtp.gmail.com", 587)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@example.com", "fake-app-password")
        mock_server.sendmail.assert_called_once()

        # Check the sendmail args
        call_args = mock_server.sendmail.call_args
        self.assertEqual(call_args[0][0], "test@example.com")  # from
        self.assertEqual(call_args[0][1], ["recipient1@example.com", "recipient2@example.com"])  # to

    @patch.dict(os.environ, {"GOOGLE_APP_PASSWORD": ""}, clear=False)
    def test_send_no_password_returns_false(self):
        """Send fails gracefully when no app password is set."""
        # Remove env var so constructor can't fall back to it
        os.environ.pop("GOOGLE_APP_PASSWORD", None)
        svc = EmailService(app_password="")
        result = svc.send("Subject", "<p>Body</p>")
        self.assertFalse(result)

    def test_send_no_recipients_returns_false(self):
        """Send fails gracefully when no recipients are provided."""
        svc = EmailService(app_password="pass", recipients=[])
        result = svc.send("Subject", "<p>Body</p>", recipients=[])
        self.assertFalse(result)

    @patch("services.email_service.smtplib.SMTP")
    def test_send_smtp_error_returns_false(self, mock_smtp_class):
        """Send returns False on SMTP error (no exception raised to caller)."""
        mock_smtp_class.return_value.__enter__ = MagicMock(
            side_effect=smtplib.SMTPAuthenticationError(535, b"Bad credentials")
        )
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = self.svc.send("Subject", "<p>Body</p>")
        self.assertFalse(result)

    # ── Convenience Method Tests ──

    @patch("services.email_service.smtplib.SMTP")
    def test_send_pr_notification(self, mock_smtp_class):
        """send_pr_notification constructs correct subject and sends."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = self.svc.send_pr_notification(
            task_title="Fix login",
            pr_url="https://github.com/user/repo/pull/42",
            project_name="TestProject",
            dispatch_id=3,
        )

        self.assertTrue(result)
        # Parse the sent MIME message to check decoded subject & body
        from email import message_from_string
        from email.header import decode_header
        sent_raw = mock_server.sendmail.call_args[0][2]
        parsed = message_from_string(sent_raw)
        subject = str(decode_header(parsed["Subject"])[0][0], "utf-8") if isinstance(decode_header(parsed["Subject"])[0][0], bytes) else decode_header(parsed["Subject"])[0][0]
        self.assertIn("PR Ready: Fix login", subject)

    @patch("services.email_service.smtplib.SMTP")
    def test_send_dispatch_status_failed(self, mock_smtp_class):
        """send_dispatch_status for failed dispatches sends correct subject."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        result = self.svc.send_dispatch_status(
            task_title="Run migrations",
            status="failed",
            dispatch_id=8,
            error_reason="Connection refused",
        )

        self.assertTrue(result)
        from email import message_from_string
        from email.header import decode_header
        sent_raw = mock_server.sendmail.call_args[0][2]
        parsed = message_from_string(sent_raw)
        subject = str(decode_header(parsed["Subject"])[0][0], "utf-8") if isinstance(decode_header(parsed["Subject"])[0][0], bytes) else decode_header(parsed["Subject"])[0][0]
        self.assertIn("Dispatch failed: Run migrations", subject)

    # ── Custom Recipients Override ──

    @patch("services.email_service.smtplib.SMTP")
    def test_send_custom_recipients(self, mock_smtp_class):
        """send() can override recipients per call."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        custom = ["custom@example.com"]
        self.svc.send("Test", "<p>Hi</p>", recipients=custom)

        call_args = mock_server.sendmail.call_args
        self.assertEqual(call_args[0][1], custom)


# Need smtplib import for the error class used in tests
import smtplib  # noqa: E402


if __name__ == "__main__":
    unittest.main()
