import resend
from django.conf import settings


def send_otp_email(user, code, otp_type):
    if otp_type == 'verify_email':
        subject = "Verify your email"
        heading = "Email Verification"
        message = "Use the code below to verify your email address."
        note = "This code expires in 10 minutes. If you didn't create an account, ignore this email."
    else:
        subject = "Reset your password"
        heading = "Password Reset"
        message = "Use the code below to reset your password."
        note = "This code expires in 10 minutes. If you didn't request a reset, ignore this email."

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin:0;padding:0;background:#f4f4f5;font-family:Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
        <tr>
          <td align="center">
            <table width="480" cellpadding="0" cellspacing="0"
                   style="background:#ffffff;border-radius:12px;overflow:hidden;
                          box-shadow:0 2px 8px rgba(0,0,0,0.08);">

              <!-- Header -->
              <tr>
                <td style="background:#4F46E5;padding:32px;text-align:center;">
                  <h1 style="margin:0;color:#ffffff;font-size:22px;">{heading}</h1>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:36px 40px;">
                  <p style="margin:0 0 8px;color:#374151;font-size:15px;">
                    Hi {user.first_name or 'there'},
                  </p>
                  <p style="margin:0 0 28px;color:#6B7280;font-size:14px;">{message}</p>

                  <!-- OTP Box -->
                  <div style="background:#F3F4F6;border-radius:10px;padding:24px;
                              text-align:center;margin-bottom:28px;">
                    <p style="margin:0 0 6px;color:#6B7280;font-size:12px;
                               letter-spacing:2px;text-transform:uppercase;">Your OTP Code</p>
                    <p style="margin:0;font-size:42px;font-weight:bold;
                               letter-spacing:12px;color:#4F46E5;">{code}</p>
                  </div>

                  <p style="margin:0;color:#9CA3AF;font-size:12px;text-align:center;">{note}</p>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="background:#F9FAFB;padding:20px 40px;text-align:center;
                            border-top:1px solid #E5E7EB;">
                  <p style="margin:0;color:#D1D5DB;font-size:11px;">
                    © 2026 InsurelyAI. All rights reserved.
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """

    resend.api_key = settings.RESEND_API_KEY

    resend.Emails.send({
        "from": settings.DEFAULT_FROM_EMAIL,
        "to": [user.email],
        "subject": subject,
        "html": html,
    })