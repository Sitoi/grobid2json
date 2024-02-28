import re

import bs4
from bs4 import BeautifulSoup, NavigableString

from grobid2json.citation_util import clear_authors, is_expansion_string
from grobid2json.grobid_util import extract_paper_metadata, parse_bib_entry
from grobid2json.refspan_util import sub_spans_and_update_indices
from grobid2json.s2orc import Paper

BRACKET_STYLE_THRESHOLD = 5
BRACKET_REGEX = re.compile(r"\[[1-9]\d{0,2}([,;\-\s]+[1-9]\d{0,2})*;?\]")
SINGLE_BRACKET_REGEX = re.compile(r"\[([1-9]\d{0,2})\]")

REPLACE_TABLE_TOKS = {
    "<row>": "<tr>",
    "<row/>": "<tr/>",
    "</row>": "</tr>",
    "<cell>": "<td>",
    "<cell/>": "<td/>",
    "</cell>": "</td>",
    "<cell ": "<td ",
    "cols=": "colspan=",
}


class UniqTokenGenerator:
    """
    Generate unique token
    """

    def __init__(self, tok_string):
        self.tok_string = tok_string
        self.ind = 0

    def __iter__(self):
        return self

    def __next__(self):
        return self.next()

    def next(self):
        new_token = f"{self.tok_string}{self.ind}"
        self.ind += 1
        return new_token


def normalize_grobid_id(grobid_id: str):
    str_norm = grobid_id.upper().replace("_", "").replace("#", "")
    if str_norm.startswith("B"):
        return str_norm.replace("B", "BIBREF")
    if str_norm.startswith("TAB"):
        return str_norm.replace("TAB", "TABREF")
    if str_norm.startswith("FIG"):
        return str_norm.replace("FIG", "FIGREF")
    if str_norm.startswith("FORMULA"):
        return str_norm.replace("FORMULA", "EQREF")
    return str_norm


def parse_bibliography(soup: BeautifulSoup) -> list[dict]:
    bibliography = soup.listBibl
    if bibliography is None:
        return []

    entries = bibliography.find_all("biblStruct")

    structured_entries = []
    for entry in entries:
        bib_entry = parse_bib_entry(entry)
        if bib_entry["title"]:
            structured_entries.append(bib_entry)

    bibliography.decompose()

    return structured_entries


def extract_formulas_from_tei_xml(sp: BeautifulSoup) -> None:
    for eq in sp.find_all("formula"):
        eq.replace_with(sp.new_string(eq.text.strip()))


def table_to_html(table: bs4.element.Tag) -> str:
    for tag in table:
        if tag.name != "row":
            print(f"Unknown table subtag: {tag.name}")
            tag.decompose()
    table_str = str(table)
    for token, subtoken in REPLACE_TABLE_TOKS.items():
        table_str = table_str.replace(token, subtoken)
    return table_str


def extract_figures_and_tables_from_tei_xml(sp: BeautifulSoup) -> dict[str, dict]:
    ref_map = dict()

    for fig in sp.find_all("figure"):
        try:
            if fig.name and fig.get("xml:id"):
                if fig.get("type") == "table":
                    ref_map[normalize_grobid_id(fig.get("xml:id"))] = {
                        "text": (
                            fig.figDesc.text.strip()
                            if fig.figDesc
                            else fig.head.text.strip()
                            if fig.head
                            else ""
                        ),
                        "latex": None,
                        "type": "table",
                        "content": table_to_html(fig.table),
                        "fig_num": fig.get("xml:id"),
                    }
                else:
                    if True in [
                        char.isdigit()
                        for char in fig.findNext("head").findNext("label")
                    ]:
                        fig_num = fig.findNext("head").findNext("label").contents[0]
                    else:
                        fig_num = None
                    ref_map[normalize_grobid_id(fig.get("xml:id"))] = {
                        "text": fig.figDesc.text.strip() if fig.figDesc else "",
                        "latex": None,
                        "type": "figure",
                        "content": "",
                        "fig_num": fig_num,
                    }
        except AttributeError:
            continue
        fig.decompose()

    return ref_map


def check_if_citations_are_bracket_style(sp: BeautifulSoup) -> bool:
    cite_strings = []
    if sp.body:
        for div in sp.body.find_all("div"):
            if div.head:
                continue
            for rtag in div.find_all("ref"):
                ref_type = rtag.get("type")
                if ref_type == "bibr":
                    cite_strings.append(rtag.text.strip())
        bracket_style = [
            bool(BRACKET_REGEX.match(cite_str)) for cite_str in cite_strings
        ]
        if sum(bracket_style) > BRACKET_STYLE_THRESHOLD:
            return True
    return False


def sub_all_note_tags(sp: BeautifulSoup) -> BeautifulSoup:
    for ntag in sp.find_all("note"):
        p_tag = sp.new_tag("p")
        p_tag.string = ntag.text.strip()
        ntag.replace_with(p_tag)
    return sp


def process_formulas_in_paragraph(para_el: BeautifulSoup, sp: BeautifulSoup) -> None:
    for ftag in para_el.find_all("formula"):
        if ftag.label:
            label = " " + ftag.label.text
            ftag.label.decompose()
        else:
            label = ""
        ftag.replace_with(sp.new_string(f"{ftag.text.strip()}{label}"))


def process_references_in_paragraph(
    para_el: BeautifulSoup, sp: BeautifulSoup, refs: dict
) -> dict:
    tokgen = UniqTokenGenerator("REFTOKEN")
    ref_dict = dict()
    for rtag in para_el.find_all("ref"):
        try:
            ref_type = rtag.get("type")
            if ref_type == "bibr":
                continue
            if ref_type == "table" or ref_type == "figure":
                ref_id = rtag.get("target")
                if ref_id and normalize_grobid_id(ref_id) in refs:
                    rtag_string = normalize_grobid_id(ref_id)
                else:
                    rtag_string = None
                ref_key = tokgen.next()
                ref_dict[ref_key] = (rtag_string, rtag.text.strip(), ref_type)
                rtag.replace_with(sp.new_string(f" {ref_key} "))
            else:
                rtag.replace_with(sp.new_string(rtag.text.strip()))
        except AttributeError:
            continue
    return ref_dict


def process_citations_in_paragraph(
    para_el: BeautifulSoup, sp: BeautifulSoup, bibs: dict, bracket: bool
) -> dict:
    def _get_surface_range(start_surface, end_surface):
        span1_match = SINGLE_BRACKET_REGEX.match(start_surface)
        span2_match = SINGLE_BRACKET_REGEX.match(end_surface)
        if span1_match and span2_match:
            span1_num = int(span1_match.group(1))
            span2_num = int(span2_match.group(1))
            if 1 < span2_num - span1_num < 20:
                return span1_num, span2_num
        return None

    def _create_ref_id_range(start_ref_id, end_ref_id):
        start_ref_num = int(start_ref_id[6:])
        end_ref_num = int(end_ref_id[6:])
        return [
            f"BIBREF{curr_ref_num}"
            for curr_ref_num in range(start_ref_num, end_ref_num + 1)
        ]

    def _create_surface_range(start_number, end_number):
        return [f"[{n}]" for n in range(start_number, end_number + 1)]

    cite_map = dict()
    tokgen = UniqTokenGenerator("CITETOKEN")

    for rtag in para_el.find_all("ref"):
        try:
            surface_span = rtag.text.strip()

            if rtag.get("target"):
                rtag_ref_id = normalize_grobid_id(rtag.get("target"))
                if rtag_ref_id not in bibs:
                    cite_key = tokgen.next()
                    rtag.replace_with(sp.new_string(f" {cite_key} "))
                    cite_map[cite_key] = (None, surface_span)
                    continue
                if bracket:
                    if surface_span and (
                        surface_span[0] == "["
                        or surface_span[-1] == "]"
                        or surface_span[-1] == ","
                    ):
                        pass
                    else:
                        rtag.replace_with(sp.new_string(f" {surface_span} "))
                        continue
                else:
                    cite_key = tokgen.next()
                    rtag.replace_with(sp.new_string(f" {cite_key} "))
                    cite_map[cite_key] = (rtag_ref_id, surface_span)
                    continue
                backward_between_span = ""
                for sib in rtag.previous_siblings:
                    if sib.name == "ref":
                        break
                    elif isinstance(sib, NavigableString):
                        backward_between_span += sib
                    else:
                        break
                if is_expansion_string(backward_between_span):
                    surface_num_range = _get_surface_range(
                        rtag.find_previous_sibling("ref").text.strip(), surface_span
                    )
                    if surface_num_range:
                        for sib in rtag.previous_siblings:
                            if sib.name == "ref":
                                break
                            elif isinstance(sib, NavigableString):
                                sib.replace_with(sp.new_string(""))
                            else:
                                break
                        previous_rtag = rtag.find_previous_sibling("ref")
                        previous_rtag_ref_id = normalize_grobid_id(
                            previous_rtag.get("target")
                        )
                        previous_rtag.decompose()
                        id_range = _create_ref_id_range(
                            previous_rtag_ref_id, rtag_ref_id
                        )
                        surface_range = _create_surface_range(
                            surface_num_range[0], surface_num_range[1]
                        )
                        replace_string = ""
                        for range_ref_id, range_surface_form in zip(
                            id_range, surface_range
                        ):
                            if range_ref_id in bibs:
                                cite_key = tokgen.next()
                                cite_map[cite_key] = (range_ref_id, range_surface_form)
                            else:
                                cite_key = tokgen.next()
                                cite_map[cite_key] = (None, range_surface_form)
                            replace_string += cite_key + " "
                        rtag.replace_with(sp.new_string(f" {replace_string} "))
                    else:
                        previous_rtag = rtag.find_previous_sibling("ref")
                        previous_rtag_ref_id = normalize_grobid_id(
                            previous_rtag.get("target")
                        )
                        previous_rtag_surface = previous_rtag.text.strip()
                        cite_key = tokgen.next()
                        previous_rtag.replace_with(sp.new_string(f" {cite_key} "))
                        cite_map[cite_key] = (
                            previous_rtag_ref_id,
                            previous_rtag_surface,
                        )
                        cite_key = tokgen.next()
                        rtag.replace_with(sp.new_string(f" {cite_key} "))
                        cite_map[cite_key] = (rtag_ref_id, surface_span)
                else:
                    forward_between_span = ""
                    for sib in rtag.next_siblings:
                        if sib.name == "ref":
                            break
                        elif isinstance(sib, NavigableString):
                            forward_between_span += sib
                        else:
                            break
                    if is_expansion_string(forward_between_span):
                        continue
                    else:
                        cite_key = tokgen.next()
                        rtag.replace_with(sp.new_string(f" {cite_key} "))
                        cite_map[cite_key] = (rtag_ref_id, surface_span)

            else:
                cite_key = tokgen.next()
                rtag.replace_with(sp.new_string(f" {cite_key} "))
                cite_map[cite_key] = (None, surface_span)
        except AttributeError:
            continue

    return cite_map


def process_paragraph(
    sp: BeautifulSoup,
    para_el: bs4.element.Tag,
    section_names: list[tuple],
    bib_dict: dict,
    ref_dict: dict,
    bracket: bool,
) -> dict:
    if not para_el.text:
        return {
            "text": "",
            "cite_spans": [],
            "ref_spans": [],
            "eq_spans": [],
            "section": section_names,
        }
    process_formulas_in_paragraph(para_el, sp)
    ref_map = process_references_in_paragraph(para_el, sp, ref_dict)
    cite_map = process_citations_in_paragraph(para_el, sp, bib_dict, bracket)
    para_text = re.sub(r"\s+", " ", para_el.text)
    para_text = re.sub(r"\s", " ", para_text)
    all_spans_to_replace = []
    for span in re.finditer(r"(CITETOKEN\d+)", para_text):
        uniq_token = span.group()
        ref_id, surface_text = cite_map[uniq_token]
        all_spans_to_replace.append(
            (span.start(), span.start() + len(uniq_token), uniq_token, surface_text)
        )
    for span in re.finditer(r"(REFTOKEN\d+)", para_text):
        uniq_token = span.group()
        ref_id, surface_text, ref_type = ref_map[uniq_token]
        all_spans_to_replace.append(
            (span.start(), span.start() + len(uniq_token), uniq_token, surface_text)
        )
    para_text, all_spans_to_replace = sub_spans_and_update_indices(
        all_spans_to_replace, para_text
    )

    cite_span_blobs = [
        {"start": start, "end": end, "text": surface, "ref_id": cite_map[token][0]}
        for start, end, token, surface in all_spans_to_replace
        if token.startswith("CITETOKEN")
    ]

    ref_span_blobs = [
        {"start": start, "end": end, "text": surface, "ref_id": ref_map[token][0]}
        for start, end, token, surface in all_spans_to_replace
        if token.startswith("REFTOKEN")
    ]

    for cite_blob in cite_span_blobs:
        assert para_text[cite_blob["start"] : cite_blob["end"]] == cite_blob["text"]

    for ref_blob in ref_span_blobs:
        assert para_text[ref_blob["start"] : ref_blob["end"]] == ref_blob["text"]

    return {
        "text": para_text,
        "cite_spans": cite_span_blobs,
        "ref_spans": ref_span_blobs,
        "eq_spans": [],
        "section": section_names,
    }


def extract_abstract_from_tei_xml(
    sp: BeautifulSoup, bib_dict: dict, ref_dict: dict, cleanup_bracket: bool
) -> list[dict]:
    abstract_text = []
    if sp.abstract:
        if sp.abstract.div:
            for div in sp.abstract.find_all("div"):
                if div.text:
                    if div.p:
                        for para in div.find_all("p"):
                            if para.text:
                                abstract_text.append(
                                    process_paragraph(
                                        sp,
                                        para,
                                        [(None, "Abstract")],
                                        bib_dict,
                                        ref_dict,
                                        cleanup_bracket,
                                    )
                                )
                    else:
                        if div.text:
                            abstract_text.append(
                                process_paragraph(
                                    sp,
                                    div,
                                    [(None, "Abstract")],
                                    bib_dict,
                                    ref_dict,
                                    cleanup_bracket,
                                )
                            )
        elif sp.abstract.p:
            for para in sp.abstract.find_all("p"):
                if para.text:
                    abstract_text.append(
                        process_paragraph(
                            sp,
                            para,
                            [(None, "Abstract")],
                            bib_dict,
                            ref_dict,
                            cleanup_bracket,
                        )
                    )
        else:
            if sp.abstract.text:
                abstract_text.append(
                    process_paragraph(
                        sp,
                        sp.abstract,
                        [(None, "Abstract")],
                        bib_dict,
                        ref_dict,
                        cleanup_bracket,
                    )
                )
        sp.abstract.decompose()
    return abstract_text


def extract_body_text_from_div(
    sp: BeautifulSoup,
    div: bs4.element.Tag,
    sections: list[tuple],
    bib_dict: dict,
    ref_dict: dict,
    cleanup_bracket: bool,
) -> list[dict]:
    chunks = []
    if div.div:
        for subdiv in div.find_all("div"):
            if subdiv.head:
                chunks += extract_body_text_from_div(
                    sp,
                    subdiv,
                    sections + [(subdiv.head.get("n", None), subdiv.head.text.strip())],
                    bib_dict,
                    ref_dict,
                    cleanup_bracket,
                )
                subdiv.head.decompose()
            else:
                chunks += extract_body_text_from_div(
                    sp, subdiv, sections, bib_dict, ref_dict, cleanup_bracket
                )
    for tag in div:
        try:
            if tag.name == "p":
                if tag.text:
                    chunks.append(
                        process_paragraph(
                            sp, tag, sections, bib_dict, ref_dict, cleanup_bracket
                        )
                    )
            elif tag.name == "formula":
                label = tag.label.text
                tag.label.decompose()
                eq_text = tag.text
                chunks.append(
                    {
                        "text": "EQUATION",
                        "cite_spans": [],
                        "ref_spans": [],
                        "eq_spans": [
                            {
                                "start": 0,
                                "end": 8,
                                "text": "EQUATION",
                                "ref_id": "EQREF",
                                "raw_str": eq_text,
                                "eq_num": label,
                            }
                        ],
                        "section": sections,
                    }
                )
        except AttributeError:
            if tag.text:
                chunks.append(
                    process_paragraph(
                        sp, tag, sections, bib_dict, ref_dict, cleanup_bracket
                    )
                )

    return chunks


def extract_body_text_from_tei_xml(
    sp: BeautifulSoup, bib_dict: dict, ref_dict: dict, cleanup_bracket: bool
) -> list[dict]:
    body_text = []
    if sp.body:
        body_text = extract_body_text_from_div(
            sp, sp.body, [], bib_dict, ref_dict, cleanup_bracket
        )
        sp.body.decompose()
    return body_text


def extract_back_matter_from_tei_xml(
    sp: BeautifulSoup, bib_dict: dict, ref_dict: dict, cleanup_bracket: bool
) -> list[dict]:
    back_text = []

    if sp.back:
        for div in sp.back.find_all("div"):
            if div.get("type"):
                section_type = div.get("type")
            else:
                section_type = ""

            for child_div in div.find_all("div"):
                if child_div.head:
                    section_title = child_div.head.text.strip()
                    section_num = child_div.head.get("n", None)
                    child_div.head.decompose()
                else:
                    section_title = section_type
                    section_num = None
                if child_div.text:
                    if child_div.text:
                        back_text.append(
                            process_paragraph(
                                sp,
                                child_div,
                                [(section_num, section_title)],
                                bib_dict,
                                ref_dict,
                                cleanup_bracket,
                            )
                        )
        sp.back.decompose()
    return back_text


def convert_xml_to_json(soup: BeautifulSoup, paper_id: str, pdf_hash: str) -> Paper:
    metadata = extract_paper_metadata(soup.fileDesc)
    metadata["authors"] = clear_authors(metadata["authors"])

    biblio_entries = parse_bibliography(soup)
    bibkey_map = {normalize_grobid_id(bib["ref_id"]): bib for bib in biblio_entries}

    refkey_map = extract_figures_and_tables_from_tei_xml(soup)

    is_bracket_style = check_if_citations_are_bracket_style(soup)

    soup = sub_all_note_tags(soup)

    abstract_entries = extract_abstract_from_tei_xml(
        soup, bibkey_map, refkey_map, is_bracket_style
    )

    body_entries = extract_body_text_from_tei_xml(
        soup, bibkey_map, refkey_map, is_bracket_style
    )

    back_matter = extract_back_matter_from_tei_xml(
        soup, bibkey_map, refkey_map, is_bracket_style
    )

    return Paper(
        paper_id=paper_id,
        pdf_hash=pdf_hash,
        metadata=metadata,
        abstract=abstract_entries,
        body_text=body_entries,
        back_matter=back_matter,
        bib_entries=bibkey_map,
        ref_entries=refkey_map,
    )
