"""Authentication-related page templates."""

from html import escape

from src.web.templates._common import _base, _csrf_field


def login_page(error: str | None = None, csrf_token: str = "") -> str:
    """Login page template."""
    error_html = ""
    if error:
        error_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Bot Admin</h1>
            {error_html}
            <form method="POST" action="/login">
                {_csrf_field(csrf_token)}
                <div class="mb-4">
                    <label for="email" class="block text-sm font-medium mb-2">
                        Email
                    </label>
                    <input
                        type="email"
                        id="email"
                        name="email"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter email"
                    >
                </div>
                <div class="mb-4">
                    <label for="password" class="block text-sm font-medium mb-2">
                        Password
                    </label>
                    <input
                        type="password"
                        id="password"
                        name="password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter password"
                    >
                </div>
                <button
                    type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors"
                >
                    Login
                </button>
            </form>
            <!-- SMTP 未設定のため非表示
            <div class="mt-4 text-center">
                <a href="/forgot-password" class="text-blue-400 hover:text-blue-300 text-sm">
                    Forgot password?
                </a>
            </div>
            -->
        </div>
    </div>
    """
    return _base("Login", content)


def forgot_password_page(
    error: str | None = None,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Forgot password page template."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Reset Password</h1>
            {message_html}
            <p class="text-gray-400 text-sm mb-4">
                Enter your email address and we'll send you a link to reset your password.
            </p>
            <form method="POST" action="/forgot-password">
                {_csrf_field(csrf_token)}
                <div class="mb-4">
                    <label for="email" class="block text-sm font-medium mb-2">
                        Email
                    </label>
                    <input
                        type="email"
                        id="email"
                        name="email"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter email"
                    >
                </div>
                <button
                    type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors"
                >
                    Send Reset Link
                </button>
            </form>
            <div class="mt-4 text-center">
                <a href="/login" class="text-gray-400 hover:text-white text-sm">
                    &larr; Back to login
                </a>
            </div>
        </div>
    </div>
    """
    return _base("Forgot Password", content)


def reset_password_page(
    token: str,
    error: str | None = None,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Reset password page template."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Set New Password</h1>
            {message_html}
            <form method="POST" action="/reset-password">
                {_csrf_field(csrf_token)}
                <input type="hidden" name="token" value="{escape(token)}">
                <div class="mb-4">
                    <label for="new_password" class="block text-sm font-medium mb-2">
                        New Password
                    </label>
                    <input
                        type="password"
                        id="new_password"
                        name="new_password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter new password"
                    >
                </div>
                <div class="mb-6">
                    <label for="confirm_password" class="block text-sm font-medium mb-2">
                        Confirm Password
                    </label>
                    <input
                        type="password"
                        id="confirm_password"
                        name="confirm_password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Confirm new password"
                    >
                </div>
                <button
                    type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors"
                >
                    Reset Password
                </button>
            </form>
            <div class="mt-4 text-center">
                <a href="/login" class="text-gray-400 hover:text-white text-sm">
                    &larr; Back to login
                </a>
            </div>
        </div>
    </div>
    """
    return _base("Reset Password", content)


def initial_setup_page(
    current_email: str,
    error: str | None = None,
    csrf_token: str = "",
) -> str:
    """Initial setup page template (requires email and password change)."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Initial Setup</h1>
            {message_html}
            <p class="text-gray-400 text-sm mb-4">
                Please set up your email address and password to continue.
            </p>
            <form method="POST" action="/initial-setup">
                {_csrf_field(csrf_token)}
                <div class="mb-4">
                    <label for="new_email" class="block text-sm font-medium mb-2">
                        Email Address
                    </label>
                    <input
                        type="email"
                        id="new_email"
                        name="new_email"
                        value="{escape(current_email)}"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter your email address"
                    >
                    <p class="text-gray-500 text-xs mt-1">
                        A verification email will be sent to this address.
                    </p>
                </div>
                <div class="mb-4">
                    <label for="new_password" class="block text-sm font-medium mb-2">
                        New Password
                    </label>
                    <input
                        type="password"
                        id="new_password"
                        name="new_password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Enter new password"
                    >
                </div>
                <div class="mb-6">
                    <label for="confirm_password" class="block text-sm font-medium mb-2">
                        Confirm Password
                    </label>
                    <input
                        type="password"
                        id="confirm_password"
                        name="confirm_password"
                        required
                        class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded
                               focus:outline-none focus:ring-2 focus:ring-blue-500
                               text-gray-100"
                        placeholder="Confirm new password"
                    >
                </div>
                <button
                    type="submit"
                    class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium
                           py-2 px-4 rounded transition-colors"
                >
                    Continue
                </button>
            </form>
        </div>
    </div>
    """
    return _base("Initial Setup", content)


def email_verification_pending_page(
    pending_email: str,
    error: str | None = None,
    success: str | None = None,
    csrf_token: str = "",
) -> str:
    """Email verification pending page template."""
    message_html = ""
    if error:
        message_html = f"""
        <div class="bg-red-500/20 border border-red-500 text-red-300 px-4 py-3 rounded mb-4">
            {escape(error)}
        </div>
        """
    elif success:
        message_html = f"""
        <div class="bg-green-500/20 border border-green-500 text-green-300 px-4 py-3 rounded mb-4">
            {escape(success)}
        </div>
        """

    content = f"""
    <div class="flex items-center justify-center min-h-screen">
        <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
            <h1 class="text-2xl font-bold text-center mb-6">Verify Your Email</h1>
            {message_html}
            <div class="text-center">
                <p class="text-gray-300 mb-4">
                    A verification email has been sent to:
                </p>
                <p class="text-blue-400 font-semibold mb-6">
                    {escape(pending_email)}
                </p>
                <p class="text-gray-400 text-sm mb-6">
                    Please check your inbox and click the verification link to continue.
                </p>
                <form method="POST" action="/resend-verification" class="mb-4">
                    {_csrf_field(csrf_token)}
                    <button
                        type="submit"
                        class="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium
                               py-2 px-4 rounded transition-colors"
                    >
                        Resend Verification Email
                    </button>
                </form>
                <a href="/logout" class="text-gray-400 hover:text-white text-sm">
                    Logout
                </a>
            </div>
        </div>
    </div>
    """
    return _base("Verify Email", content)
