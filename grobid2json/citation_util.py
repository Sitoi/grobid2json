def is_expansion_string(between_string: str) -> bool:
    EXPANSION_CHARS = {"-", "–"}
    if (
        len(between_string) <= 2
        and any([c in EXPANSION_CHARS for c in between_string])
        and all([c in EXPANSION_CHARS.union({" "}) for c in between_string])
    ):
        return True
    return False


def clear_authors(
    authors: list[dict],
) -> list[dict]:
    clean_authors_list = []
    for author in authors:
        clean_first = author["first"].strip()
        clean_last = author["last"].strip()
        clean_middle = [m.strip() for m in author["middle"]]
        clean_suffix = author["suffix"].strip()
        if clean_first or clean_last or clean_middle:
            author["first"] = clean_first
            author["last"] = clean_last
            author["middle"] = clean_middle
            author["suffix"] = clean_suffix
            clean_authors_list.append(author)
    key_to_author_blobs = {}
    ordered_keys_by_author_pos = []
    for author in clean_authors_list:
        key = (
            author["first"],
            author["last"],
            " ".join(author["middle"]),
            author["suffix"],
        )
        if key not in key_to_author_blobs:
            key_to_author_blobs[key] = author
            ordered_keys_by_author_pos.append(key)
        else:
            if author["email"]:
                key_to_author_blobs[key]["email"] = author["email"]
            if author["affiliation"] and (
                author["affiliation"]["institution"]
                or author["affiliation"]["laboratory"]
                or author["affiliation"]["location"]
            ):
                key_to_author_blobs[key]["affiliation"] = author["affiliation"]
    dedup_authors_list = [
        key_to_author_blobs[key] for key in ordered_keys_by_author_pos
    ]
    return dedup_authors_list
