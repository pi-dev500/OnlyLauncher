import sys
import json
import uuid
from pathlib import Path
from urllib.parse import urlencode, parse_qs, urlparse
from typing import Optional, Callable
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import secrets
import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QStackedWidget
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QLinearGradient, QColor, QPalette, QPixmap, QPainter
from PyQt6.QtCore import QSize

# PortableMC imports (correct API)
from portablemc.auth import MicrosoftAuthSession, AuthError


class RedirectHandler(BaseHTTPRequestHandler):
    """HTTP handler for OAuth redirect"""
    
    redirect_data = None
    
    def do_POST(self):
        """Handle POST request from Microsoft redirect with form-encoded body"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        params = parse_qs(body)
        redirect_data = {key: value[0] if isinstance(value, list) else value 
                        for key, value in params.items()}
        
        RedirectHandler.redirect_data = redirect_data
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        
        html = """
        <html>
        <head>
            <title>Processing Login</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }
                .container {
                    text-align: center;
                    color: #fff;
                }
                h1 {
                    color: #fff;
                    margin-bottom: 10px;
                    font-size: 24px;
                }
                p {
                    font-size: 15px;
                    margin: 10px 0;
                    color: rgba(255, 255, 255, 0.9);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Authentication Successful</h1>
                <p>Processing your login information...</p>
                <p>You can close this window and return to the launcher.</p>
            </div>
        </body>
        </html>
        """
        
        self.wfile.write(html.encode('utf-8'))
    
    def log_message(self, format, *args):
        pass


class GradientWidget(QWidget):
    """Widget with modern Microsoft gradient background"""
    
    def __init__(self):
        super().__init__()
        self.gradient_pixmap = None
        self.create_gradient()
    
    def create_gradient(self):
        """Create a modern Microsoft-like gradient background"""
        pixmap = QPixmap(1920, 1080)
        painter = QPainter(pixmap)
        
        # Create gradient similar to modern Microsoft login
        gradient = QLinearGradient(0, 0, 1920, 1080)
        
        # Modern colors: blues, purples, greens
        gradient.setColorAt(0.0, QColor(102, 126, 234))      # Blue
        gradient.setColorAt(0.3, QColor(118, 75, 162))       # Purple
        gradient.setColorAt(0.6, QColor(99, 179, 156))       # Green
        gradient.setColorAt(1.0, QColor(66, 155, 245))       # Light Blue
        
        painter.fillRect(pixmap.rect(), gradient)
        painter.end()
        
        self.gradient_pixmap = pixmap
    
    def paintEvent(self, event):
        """Paint the gradient background"""
        if self.gradient_pixmap:
            painter = QPainter(self)
            scaled = self.gradient_pixmap.scaled(self.size())
            painter.drawPixmap(0, 0, scaled)
        super().paintEvent(event)


class ResultWidget(QWidget):
    """Widget to display success or failure result"""
    
    def __init__(self, is_success: bool, details: str = ""):
        super().__init__()
        self.setStyleSheet("background-color: transparent;")
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Centered box
        box = QWidget()
        box.setStyleSheet("""
            QWidget {
                background-color: #fff;
                border-radius: 8px;
            }
        """)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(40, 40, 40, 40)
        box_layout.setSpacing(16)
        
        # Title
        title = QLabel("Success!" if is_success else "Authentication Failed")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title.setFont(title_font)
        
        if is_success:
            title.setStyleSheet("color: #107c10;")
        else:
            title.setStyleSheet("color: #da3b01;")
        
        box_layout.addWidget(title)
        
        # Message
        if is_success:
            message = "Your authentication was successful!"
        else:
            message = "We couldn't complete your authentication."
        
        message_label = QLabel(message)
        message_label.setStyleSheet("font-size: 15px; color: #333; margin: 8px 0;")
        box_layout.addWidget(message_label)
        
        # Details
        if details:
            details_label = QLabel(details)
            details_label.setStyleSheet("font-size: 13px; color: #666; white-space: pre-wrap; margin-top: 12px;")
            details_label.setWordWrap(True)
            box_layout.addWidget(details_label)
        
        # Info
        if is_success:
            info_label = QLabel("Your credentials have been saved.\nYou can close this window.")
        else:
            info_label = QLabel("Please check your credentials and try again.\nYou can close this window.")
        
        info_label.setStyleSheet("font-size: 13px; color: #666; margin-top: 20px;")
        box_layout.addWidget(info_label)
        
        layout.addStretch()
        layout.addWidget(box, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()


class MicrosoftLoginWindow(QMainWindow):
    """
    PortableMC Microsoft Login window using PyQt6
    Modern login.live.com design with gradient background
    """
    
    def __init__(self, app_id: str, cache_dir: Optional[str] = None, parent=None, on_complete: Optional[Callable] = None):
        super().__init__(parent)
        
        self.app_id = app_id
        self.cache_dir = Path(cache_dir or "./minecraft_auth")
        self.cache_dir.mkdir(exist_ok=True)
        
        self.redirect_uri = "http://localhost:7969/code"
        self.client_id = str(uuid.uuid4())
        self.nonce = secrets.token_urlsafe(32)
        
        self.on_complete = on_complete
        self.auth_data = None
        self.is_authenticating = False
        self.check_redirect_timer = None
        
        self.setWindowTitle("Microsoft Account")
        self.setGeometry(100, 100, 1200, 800)
        
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # Page 0: Modern login form
        self.login_form = self.create_modern_login_form()
        self.stacked_widget.addWidget(self.login_form)
        
        # Page 1: Web view
        self.web_view = QWebEngineView()
        self.stacked_widget.addWidget(self.web_view)
        
        # Page 2: Result
        self.result_widget = None
        
        self.load_cached_email()
    
    def create_modern_login_form(self) -> QWidget:
        """Create modern Microsoft login form with gradient background"""
        main_widget = GradientWidget()
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Add stretches and centered form box
        layout.addStretch()
        
        # Form box
        form_box = QWidget()
        form_box.setStyleSheet("""
            QWidget {
                background-color: #fff;
                border-radius: 8px;
            }
        """)
        form_box.setMaximumWidth(400)
        
        form_layout = QVBoxLayout(form_box)
        form_layout.setContentsMargins(40, 40, 40, 40)
        form_layout.setSpacing(16)
        
        # Microsoft logo
        logo = QLabel("microsoft")
        logo_font = QFont()
        logo_font.setPointSize(16)
        logo_font.setBold(True)
        logo.setFont(logo_font)
        logo.setStyleSheet("color: #00a4ef; margin-bottom: 8px;")
        form_layout.addWidget(logo)
        
        # Title
        title = QLabel("Sign in")
        title_font = QFont()
        title_font.setPointSize(28)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #000; margin-bottom: 8px;")
        form_layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Minecraft Account Authentication")
        subtitle.setStyleSheet("color: #666; font-size: 13px; margin-bottom: 16px;")
        form_layout.addWidget(subtitle)
        
        # Email input
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email, phone, or Skype")
        self.email_input.setMinimumHeight(44)
        self.email_input.setStyleSheet("""
            QLineEdit {
                background-color: #fff;
                border: 1px solid #ccc;
                border-radius: 4px;
                color: #000;
                padding: 10px 12px;
                font-size: 15px;
            }
            QLineEdit:focus {
                border: 2px solid #00a4ef;
                outline: none;
            }
        """)
        self.email_input.returnPressed.connect(self.start_login)

        form_layout.addWidget(self.email_input)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #999; font-size: 12px; height: 16px;")
        form_layout.addWidget(self.status_label)
        
        # Next button
        self.login_button = QPushButton("Next")
        self.login_button.setMinimumHeight(40)
        self.login_button.setStyleSheet("""
            QPushButton {
                background-color: #00a4ef;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: #0078d4;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        self.login_button.clicked.connect(self.start_login)
        form_layout.addWidget(self.login_button)
        
        # Links at bottom
        links_layout = QHBoxLayout()
        links_layout.setSpacing(12)
        
        cant_access = QLabel('<a href="#">Can\'t access your account?</a>')
        cant_access.setOpenExternalLinks(False)
        cant_access.setStyleSheet("color: #00a4ef; font-size: 13px;")
        links_layout.addWidget(cant_access)
        
        links_layout.addStretch()
        
        sign_up = QLabel('<a href="#">Sign up</a>')
        sign_up.setOpenExternalLinks(False)
        sign_up.setStyleSheet("color: #00a4ef; font-size: 13px;")
        links_layout.addWidget(sign_up)
        
        form_layout.addLayout(links_layout)
        
        # Center the form box
        form_container = QWidget()
        form_container_layout = QHBoxLayout(form_container)
        form_container_layout.setContentsMargins(0, 0, 0, 0)
        form_container_layout.addStretch()
        form_container_layout.addWidget(form_box)
        form_container_layout.addStretch()
        
        layout.addWidget(form_container)
        layout.addStretch()
        
        return main_widget
    
    def load_cached_email(self):
        """Load cached email from previous login"""
        creds_file = self.cache_dir / "credentials.json"
        if creds_file.exists():
            try:
                with open(creds_file, "r") as f:
                    data = json.load(f)
                    if "email" in data:
                        self.email_input.setText(data["email"])
            except Exception as e:
                print(f"Could not load cached email: {e}")
    
    def start_login(self):
        """Start the Microsoft OAuth login flow"""
        if self.is_authenticating:
            return
        
        email = self.email_input.text().strip()
        if not email:
            self.status_label.setText("Enter an email address")
            self.status_label.setStyleSheet("color: #da3b01; font-size: 12px;")
            return
        
        if "@" not in email:
            self.status_label.setText("Enter a valid email address")
            self.status_label.setStyleSheet("color: #da3b01; font-size: 12px;")
            return
        
        self.is_authenticating = True
        self.email = email
        self.login_button.setEnabled(False)
        self.email_input.setEnabled(False)
        self.status_label.setText("Opening Microsoft login...")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        
        try:
            def run_server():
                try:
                    server = HTTPServer(('localhost', 7969), RedirectHandler)
                    server.timeout = 600
                    server.handle_request()
                    server.server_close()
                except Exception as e:
                    print(f"Server error: {e}")
            
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            
            auth_url = MicrosoftAuthSession.get_authentication_url(
                self.app_id,
                self.redirect_uri,
                email=email,
                nonce=self.nonce
            )
            
            self.stacked_widget.setCurrentIndex(1)
            self.web_view.load(QUrl(auth_url))
            
            self.check_redirect_timer = QTimer()
            self.check_redirect_timer.timeout.connect(self.check_for_redirect_data)
            self.check_redirect_timer.start(100)
            
        except Exception as e:
            self.show_result(False, f"Error: {str(e)}")
            self.is_authenticating = False
            self.login_button.setEnabled(True)
            self.email_input.setEnabled(True)
    
    def check_for_redirect_data(self):
        """Check if redirect data has been received"""
        if RedirectHandler.redirect_data:
            self.check_redirect_timer.stop()
            redirect_data = RedirectHandler.redirect_data
            RedirectHandler.redirect_data = None
            self.extract_and_complete_login(redirect_data)
    
    def extract_and_complete_login(self, redirect_data: dict):
        """Extract tokens and complete login with full validation"""
        try:
            if "error" in redirect_data:
                error = redirect_data["error"]
                error_desc = redirect_data.get("error_description", "Unknown error")
                self.show_result(False, f"Microsoft error: {error}\n{error_desc}")
                return
            
            if "code" not in redirect_data or "id_token" not in redirect_data:
                self.show_result(False, "Missing authorization code or token from redirect")
                return
            
            code = redirect_data["code"]
            id_token = redirect_data["id_token"]
            
            if not MicrosoftAuthSession.check_token_id(id_token, self.email, self.nonce):
                self.show_result(False, "Token validation failed: Invalid token data")
                return
            
            try:
                auth_session = MicrosoftAuthSession.authenticate(
                    self.client_id,
                    self.app_id,
                    code,
                    self.redirect_uri
                )
            except AuthError as e:
                self.show_result(False, f"Minecraft account error: {str(e)}\n\nYour account may not have Minecraft.")
                return
            
            if not auth_session or not auth_session.profile or not auth_session.access_token:
                self.show_result(False, "Failed to retrieve Minecraft profile")
                return
            
            auth_data = {
                "type": "microsoft",
                "email": self.email,
                "client_id": self.client_id,
                "app_id": self.app_id,
                "profile_name": auth_session.profile.name,
                "profile_uuid": str(auth_session.profile.uuid),
                "access_token": auth_session.access_token,
                "timestamp": str(datetime.datetime.now()),
            }
            
            try:
                creds_file = self.cache_dir / "credentials.json"
                with open(creds_file, "w") as f:
                    json.dump(auth_data, f, indent=2)
            except Exception as e:
                self.show_result(False, f"Failed to save credentials: {str(e)}")
                return
            
            self.auth_data = auth_data
            details = f"Profile: {auth_data['profile_name']}\nUUID: {auth_data['profile_uuid']}\nEmail: {auth_data['email']}"
            self.show_result(True, details)
            
        except Exception as e:
            self.show_result(False, f"Unexpected error: {str(e)}")
    
    def show_result(self, is_success: bool, details: str):
        """Show result page (success or failure)"""
        self.is_authenticating = False
        
        self.result_widget = ResultWidget(is_success, details)
        self.stacked_widget.addWidget(self.result_widget)
        self.stacked_widget.setCurrentIndex(2)
        
        if is_success:
            QTimer.singleShot(5000, self.close)
        
        if self.on_complete:
            self.on_complete(is_success, self.auth_data if is_success else None)


class PortableMCLauncher:
    """Main launcher class integrating the login window"""
    
    def __init__(self, app_id: str, cache_dir: Optional[str] = None):
        self.app_id = app_id
        self.cache_dir = Path(cache_dir or "./minecraft_auth")
        self.cache_dir.mkdir(exist_ok=True)
        self.auth_window = None
    
    def show_login_window(self, on_complete: Optional[Callable] = None) -> Optional[dict]:
        """Display the Microsoft login window"""
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        
        result_auth_data = None
        
        def completion_callback(success: bool, auth_data: dict):
            nonlocal result_auth_data
            if success:
                result_auth_data = auth_data
            if on_complete:
                on_complete(success, auth_data)
        
        self.auth_window = MicrosoftLoginWindow(self.app_id, self.cache_dir, on_complete=completion_callback)
        self.auth_window.show()
        
        app.exec()
        return result_auth_data
    
    def load_cached_credentials(self) -> Optional[dict]:
        """Load previously saved credentials"""
        creds_file = self.cache_dir / "credentials.json"
        
        if creds_file.exists():
            try:
                with open(creds_file, "r") as f:
                    data = json.load(f)
                    print(f"✓ Loaded cached credentials for: {data.get('profile_name', 'Unknown')}")
                    return data
            except Exception as e:
                print(f"✗ Failed to load cached credentials: {e}")
        
        return None
    
    def clear_cached_credentials(self):
        """Clear cached credentials"""
        creds_file = self.cache_dir / "credentials.json"
        if creds_file.exists():
            try:
                creds_file.unlink()
                print(f"✓ Cleared cached credentials")
            except Exception as e:
                print(f"✗ Failed to clear credentials: {e}")


# Example usage
if __name__ == "__main__":
    PORTABLEMC_APP_ID = "708e91b5-99f8-4a1d-80ec-e746cbb24771"
    
    launcher = PortableMCLauncher(PORTABLEMC_APP_ID, cache_dir="./minecraft_auth")
    
    def on_auth_complete(success: bool, auth_data: dict):
        if success:
            print(f"\n✓ Authentication successful!")
            print(f"  Profile: {auth_data['profile_name']}")
            print(f"  UUID: {auth_data['profile_uuid']}")
            print(f"  Email: {auth_data['email']}")
        else:
            print(f"\n✗ Authentication failed!")
    
    cached = launcher.load_cached_credentials()
    if cached:
        print(f"  UUID: {cached['profile_uuid']}")
        print(f"  Saved: {cached.get('timestamp', 'unknown')}")
    
    result = launcher.show_login_window(on_complete=on_auth_complete)
    
    if result:
        print(f"\nAuth data returned: {result['profile_name']}")
    else:
        print("\nNo authentication data returned")
