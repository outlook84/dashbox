from importlib.metadata import PackageNotFoundError, metadata, version

__all__ = ["__project_url__", "__version__"]

try:
    __version__ = version("dashbox")
except PackageNotFoundError:
    __version__ = "0+unknown"


def _project_url() -> str:
    try:
        package_metadata = metadata("dashbox")
    except PackageNotFoundError:
        return ""

    project_urls = package_metadata.get_all("Project-URL") or []
    for preferred_label in ("Source", "Homepage"):
        for entry in project_urls:
            label, separator, url = entry.partition(",")
            if separator and label.strip().lower() == preferred_label.lower():
                return url.strip()

    home_page = package_metadata.get("Home-page", "")
    return str(home_page).strip()


__project_url__ = _project_url()
