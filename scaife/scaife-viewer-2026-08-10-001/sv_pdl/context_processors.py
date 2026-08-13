import os


def google_analytics(request):
    # Removed hardcoded Perseus Digital Library GA tracking codes so this
    # public fork doesn't accidentally report to their analytics account.
    # If you want GA on your local fork, set SCAIFE_GA_CODE in the env.
    return {
        "ga_code": os.environ.get("SCAIFE_GA_CODE") or None,
    }
