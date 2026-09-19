from app.downloader import _find_image_post_nodes, _walk_image_urls


def test_extracts_tiktok_image_post_urls_from_payload():
    payload = {
        "itemInfo": {
            "itemStruct": {
                "imagePost": {
                    "images": [
                        {"imageURL": {"urlList": ["https://p16.tiktokcdn.com/a.jpeg"]}},
                        {"imageURL": {"urlList": ["https://p16.tiktokcdn.com/b.jpeg"]}},
                    ]
                }
            }
        }
    }
    nodes = []
    _find_image_post_nodes(payload, nodes)
    assert len(nodes) == 1
    urls = []
    _walk_image_urls(nodes[0], urls)
    assert urls == [
        "https://p16.tiktokcdn.com/a.jpeg",
        "https://p16.tiktokcdn.com/b.jpeg",
    ]
