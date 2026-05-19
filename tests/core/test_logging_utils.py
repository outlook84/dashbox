from dashbox.utils.errors import exception_reason


def test_exception_reason_removes_traceback_lines_and_local_paths() -> None:
    cases = (
        (
            RuntimeError(
                'Traceback (most recent call last):\n'
                'File "C:\\Users\\anshi\\Desktop\\git\\yt-dlp\\yt_dlp\\YoutubeDL.py", line 123, in extract_info\n'
                "ERROR: [youtube] abc: Sign in to confirm you are not a bot\n"
                "See C:\\Users\\anshi\\Desktop\\git\\yt-dlp\\yt_dlp\\extractor\\youtube.py for details"
            ),
            ("Traceback", "C:\\Users"),
            ("<path>", "Sign in to confirm"),
            1,
        ),
        (
            RuntimeError("See /home/dashbox/yt_dlp/extractor/youtube.py for details"),
            ("/home/dashbox",),
            ("<path>",),
            1,
        ),
        (
            RuntimeError(
                "WindowsPath('C:\\Users\\name\\cookies.sqlite') "
                "PosixPath('/home/name/file') "
                "source=C:\\Users\\name\\Downloads\\video.mp4"
            ),
            ("C:\\Users", "/home/name"),
            ("WindowsPath('<path>')", "PosixPath('<path>')", "source=<path>"),
            3,
        ),
        (
            RuntimeError("failed file:///C:/Users/name/cookies.sqlite and file:///home/name/cookies.sqlite"),
            ("C:/Users/name", "/home/name"),
            ("<path>",),
            2,
        ),
    )

    for exc, forbidden, required, path_count in cases:
        reason = exception_reason(exc)
        for value in forbidden:
            assert value not in reason
        for value in required:
            assert value in reason
        assert reason.count("<path>") == path_count


def test_exception_reason_preserves_urls() -> None:
    reason = exception_reason(RuntimeError("failed https://example.test/a/b?x=1 and http://cdn.example.test/img/1.jpg"))

    assert "https://example.test/a/b?x=1" in reason
    assert "http://cdn.example.test/img/1.jpg" in reason
    assert "<path>" not in reason


def test_exception_reason_truncates_long_messages() -> None:
    reason = exception_reason(ValueError("x" * 500), max_length=20)

    assert reason == "xxxxxxxxxxxxxxxxx..."


def test_exception_reason_uses_exception_type_for_empty_message() -> None:
    assert exception_reason(RuntimeError()) == "RuntimeError"
