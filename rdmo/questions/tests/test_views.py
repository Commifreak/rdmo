import xml.etree.ElementTree as et

import pytest
from django.urls import reverse

users = (
    ('user', 'user'),
    ('anonymous', None),
    ('site', 'site')
)

groups = (
    ('editor', 'editor'),
    ('reviewer', 'reviewer'),
    ('api', 'api'),
)

status_map = {
    'catalogs': {
        'site': 200, 'user': 403, 'anonymous': 302
    },
    'questions_catalog_export': {
        'site': 200, 'user': 403, 'anonymous': 302
    }
}

catalog_pk = 1

export_formats = ('xml', 'rtf', 'odt', 'docx', 'html', 'markdown', 'tex', 'pdf')


@pytest.mark.parametrize('username,password', users)
def test_questions(db, client, username, password):
    client.login(username=username, password=password)

    url = reverse('catalogs')
    response = client.get(url)
    assert response.status_code == status_map['catalogs'][username]


@pytest.mark.parametrize('username,password', users)
@pytest.mark.parametrize('export_format', export_formats)
def test_questions_export(db, client, username, password, export_format):
    client.login(username=username, password=password)

    url = reverse('questions_catalog_export', args=[catalog_pk, export_format])
    response = client.get(url)
    assert response.status_code == status_map['questions_catalog_export'][username]

    if response.status_code == 200:
        if export_format == 'xml':
            root = et.fromstring(response.content)
            assert root.tag == 'rdmo'
            for child in root:
                assert child.tag in ['catalog', 'section', 'questionset', 'question']
