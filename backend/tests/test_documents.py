from app.services.documents import chunk_text, extract_keywords, extract_text


def test_text_extraction_chunking_and_keywords():
    text = extract_text("notes.txt", b"Photosynthesis uses light.\n\nChlorophyll captures energy.")

    chunks = chunk_text(text, chunk_size=40, overlap=5)
    keywords = extract_keywords(text)

    assert "Photosynthesis" in text
    assert chunks
    assert "photosynthesis" in keywords


def test_chunking_preserves_page_and_slide_sections():
    text = "[page 2]\nPhotosynthesis uses chlorophyll.\n\n[slide 4]\nThe Calvin cycle builds sugar."

    chunks = chunk_text(text, chunk_size=80, overlap=10)

    assert chunks[0]["section"].startswith("page 2")
    assert chunks[1]["section"].startswith("slide 4")
    assert "[page 2]" in chunks[0]["text"]
    assert "[slide 4]" in chunks[1]["text"]
