.PHONY: clean sdist upload pre-commit

sdist: clean
	python3 setup.py sdist bdist_wheel --universa

upload: clean
	python3 setup.py upload

clean:
	rm -rf build grobid2json.egg-info dist

pre-commit:
	pre-commit run --all-files
