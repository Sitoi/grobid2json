<a name="readme-top"></a>

<div align="center">

<h1>Grobid2Json</h1>

Extract the code to parse grobid xml into json from the s2orc-doc2json project and package it as a pypi package.

<!-- SHIELD GROUP -->

[![][github-forks-shield]][github-forks-link]
[![][github-stars-shield]][github-stars-link]
[![][github-issues-shield]][github-issues-link]
[![][github-license-shield]][github-license-link]

</div>

## ✨ Features

- Process the XML files parsed by Grobid into JSON format.

## 📦 Installation

```bash
pip install grobid2json
```

## 🤯 Usage

```python
from bs4 import BeautifulSoup
from grobid2json import convert_xml_to_json

file_path = "test.xml"
with open(file_path, "rb") as f:
    xml_data = f.read()
soup = BeautifulSoup(xml_data, "xml")
paper_id = file_path.split("/")[-1].split(".")[0]
paper = convert_xml_to_json(soup, paper_id, "")
json_data = paper.as_json()
print(json_data)
```

## 🔗 Links

### Credits

- **s2orc-doc2json** - <https://github.com/allenai/s2orc-doc2json>

---

## 📝 License

This project is [Apache License 2.0](./LICENSE) licensed.

<!-- LINK GROUP -->

[github-forks-link]: https://github.com/sitoi/grobid2json/network/members
[github-forks-shield]: https://img.shields.io/github/forks/sitoi/grobid2json?color=8ae8ff&labelColor=black&style=flat-square
[github-issues-link]: https://github.com/sitoi/grobid2json/issues
[github-issues-shield]: https://img.shields.io/github/issues/sitoi/grobid2json?color=ff80eb&labelColor=black&style=flat-square
[github-license-link]: https://github.com/sitoi/grobid2json/blob/main/LICENSE
[github-license-shield]: https://img.shields.io/github/license/sitoi/grobid2json?color=white&labelColor=black&style=flat-square
[github-stars-link]: https://github.com/sitoi/grobid2json/network/stargazers
[github-stars-shield]: https://img.shields.io/github/stars/sitoi/grobid2json?color=ffcb47&labelColor=black&style=flat-square
