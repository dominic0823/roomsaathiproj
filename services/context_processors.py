def compare_tray(request):
    ids = request.session.get("compare", []) if hasattr(request, "session") else []
    return {"compare_ids": ids}
