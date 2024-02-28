def replace_refspans(
    spans_to_replace: list[tuple[int, int, str, str]],
    full_string: str,
    pre_padding: str = "",
    post_padding: str = "",
    btwn_padding: str = ", ",
) -> str:
    assert all(
        [full_string[start:end] == span for start, end, span, _ in spans_to_replace]
    )
    start_inds = [rep[0] for rep in spans_to_replace]
    assert len(set(start_inds)) == len(start_inds)
    spans_to_replace.sort(key=lambda x: x[0])
    for i, entry in enumerate(spans_to_replace):
        start, end, span, new_string = entry
        if end <= 0:
            continue
        shift_amount = (
            len(new_string) - len(span) + len(pre_padding) + len(post_padding)
        )
        for ind in range(i + 1, len(spans_to_replace)):
            next_start, next_end, next_span, next_string = spans_to_replace[ind]
            if next_end <= 0:
                continue
            if next_start < end:
                next_start = 0
                next_end = 0
                next_string = ""
            elif next_start == end:
                next_start += shift_amount
                next_end += shift_amount
                next_string = btwn_padding + pre_padding + next_string + post_padding
            elif next_start > end:
                next_start += shift_amount
                next_end += shift_amount
                next_string = pre_padding + next_string + post_padding
            spans_to_replace[ind] = (next_start, next_end, next_span, next_string)

    spans_to_replace = [entry for entry in spans_to_replace if entry[1] > 0]
    spans_to_replace.sort(key=lambda x: x[0])
    for start, end, span, new_string in spans_to_replace:
        assert full_string[start:end] == span
        full_string = full_string[:start] + new_string + full_string[end:]
    return full_string


def sub_spans_and_update_indices(
    spans_to_replace: list[tuple[int, int, str, str]], full_string: str
) -> tuple[str, list]:
    assert all(
        [full_string[start:end] == token for start, end, token, _ in spans_to_replace]
    )
    start_inds = [rep[0] for rep in spans_to_replace]
    assert len(set(start_inds)) == len(start_inds)
    spans_to_replace.sort(key=lambda x: x[0])
    new_spans = [
        [start, end, token, surface, 0]
        for start, end, token, surface in spans_to_replace
    ]
    for i, entry in enumerate(spans_to_replace):
        start, end, token, surface = entry
        new_end = start + len(surface)
        offset = new_end - end
        new_spans[i][1] += offset
        for new_span_entry in new_spans[i + 1 :]:
            new_span_entry[4] += offset
    new_text = replace_refspans(spans_to_replace, full_string, btwn_padding="")
    new_spans = [
        (start + offset, end + offset, token, surface)
        for start, end, token, surface, offset in new_spans
    ]

    return new_text, new_spans
