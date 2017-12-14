#!/usr/bin/env python

import csv
import io
import re
import sys

import requests
import lxml.html

from os.path import dirname, join as pjoin

CURRENT_URL = 'http://www.suttonkersh.co.uk/properties/listview/?section=auction&auctionPeriod=current&perPage=all'  # noqa

TABLE_ROW_XPATH = "//tr[contains(@id, 'header_')]"

PAGE_ENCODING = 'utf-8'

FIELDS = (
    'lot_number',
    'street_address',
    'postcode',
    'status',
    'guide_price_low',
    'guide_price_high',
    '_yield_guide_price_high',
    '_price_10pct_yield',
    '_price_12.5pct_yield',
    '_price_15pct_yield',
    '_price_20pct_yield',
    'has_assured_shorthold_tenancy',
    'ast_annual_income',
    'description',
    'detail_url',
    'photo_url',

)


def main(html_filename=None):

    if html_filename:
        html_string = html_from_file(html_filename)
    else:
        html_string = html_from_url(CURRENT_URL)

    output_csv(get_rows_from_page(html_string))


def html_from_file(html_filename):
    with io.open(html_filename, 'rb') as f:
        return f.read().decode(PAGE_ENCODING)


def html_from_url(url):
    response = requests.get(url)
    response.raise_for_status()

    write_back_page_to_file(response)

    return response.text


def write_back_page_to_file(response):
    assert response.encoding == PAGE_ENCODING, response.encoding

    with io.open(pjoin(dirname(__file__), 'sample_page.html'), 'wb') as f:
        f.write(response.content)


def output_csv(rows):
    writer = csv.DictWriter(sys.stdout, FIELDS)
    writer.writeheader()

    for row in rows:
        writer.writerow(row)


class PropertyRowParser():
    DESCRIPTION_P = ".//p[contains(@class, 'descriptionText')]"

    def __init__(self, header_tr):
        self.header_tr = header_tr
        self.detail_tr = header_tr.xpath('./following-sibling::tr')[0]

    @staticmethod
    def text(list_of_one_element):
        """
        Return the stripped text_content() of the one-and-only xpath result
        """
        if isinstance(list_of_one_element, list):
            assert len(list_of_one_element) == 1, list_of_one_element
            element = list_of_one_element[0]
        else:
            element = list_of_one_element

        return element.text_content().strip()

    @staticmethod
    def price(price_string):
        return int(float(price_string.replace(',', '').strip()))

    @staticmethod
    def _make_absolute_url(path):
        return 'http://www.suttonkersh.co.uk{}'.format(path)

    @property
    def lot_number(self):
        return self.text(self.header_tr.xpath('./td')[0])

    @property
    def street_address(self):
        return self.text(self.header_tr.xpath('./td')[1])

    @property
    def postcode(self):
        return self.text(self.header_tr.xpath('./td')[2])

    @property
    def status(self):
        return self.text(self.header_tr.xpath('./td')[3])

    @property
    def description(self):
        return self.detail_tr.xpath(
            self.DESCRIPTION_P
        )[0].text_content()

    @property
    def guide_price_low(self):
        return self._parse_guide_price_range()[0]

    @property
    def guide_price_high(self):
        return self._parse_guide_price_range()[1]

    @property
    def has_assured_shorthold_tenancy(self):
        return 'assured shorthold' in self.description.lower()

    @property
    def ast_annual_income(self):
        """
        '£15,400 per annum'
        """
        if not self.has_assured_shorthold_tenancy:
            return

        match = re.search(
            '£(?P<income>[0-9,.]+) per annum',
            self.description
        )
        if match is not None:
            return self.price(match.group('income'))

    @property
    def detail_url(self):
        return self._make_absolute_url(
            self.detail_tr.xpath(
                ".//a[contains(text(), 'Details')]"
                )[0].attrib['href']
        )

    @property
    def photo_url(self):
        return self._make_absolute_url(
            self.detail_tr.xpath(
                ".//img[contains(@class, 'lotImage')]"
            )[0].attrib['src']
        )

    def _parse_guide_price_range(self):
        status = self.status

        match = re.match(
            r'Guide Price: £(?P<low>[0-9,]+).+£(?P<high>[0-9,]+)\*$', status
        )

        if match is not None:
            return (
                self.price(match.group('low')),
                self.price(match.group('high'))
            )

        match = re.match(r'Guide Price: £(?P<price>[0-9,]+)\+\*$', status)
        if match is not None:
            price = self.price(match.group('price'))
            return (price, price)

        return (None, None)

    def as_dict(self):
        return {
            'lot_number': self.lot_number,
            'street_address': self.street_address,
            'postcode': self.postcode,
            'status': self.status,
            'description': self.description,
            'detail_url': self.detail_url,
            'photo_url': self.photo_url,

            'guide_price_low': self.guide_price_low,
            'guide_price_high': self.guide_price_high,
            'has_assured_shorthold_tenancy': self.has_assured_shorthold_tenancy,
            'ast_annual_income': self.ast_annual_income,
        }


def get_rows_from_page(html):
    root = lxml.html.fromstring(html)
    for tr in root.xpath(TABLE_ROW_XPATH):
        row = PropertyRowParser(tr).as_dict()

        add_calculations(row)

        yield row


def add_calculations(row):
    annual_income = row['ast_annual_income']
    guide_price_high = row['guide_price_high']

    if annual_income:
        row['_price_10pct_yield'] = annual_income / 0.10
        row['_price_12.5pct_yield'] = annual_income / 0.125
        row['_price_15pct_yield'] = annual_income / 0.15
        row['_price_20pct_yield'] = annual_income / 0.20

        if guide_price_high:
            row['_yield_guide_price_high'] = (guide_price_high / annual_income) / 100


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
