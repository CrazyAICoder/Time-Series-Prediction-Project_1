import loudml.vendor

import datetime
import logging
import numpy as np
import os
import time
import unittest

logging.getLogger('tensorflow').disabled = True

import loudml.errors as errors
try:
    import loudml.test
except ImportError as exn:
    # ignore fingerprint import error
    print("warning:", exn)

from loudml.elastic import ElasticsearchDataSource

from loudml.timeseries import (
    TimeSeriesModel,
    TimeSeriesPrediction,
)

TEMPLATE = {
    "template": "test-*",
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "codec":"best_compression"
    },
    "mappings": {
        "doc": {
            "include_in_all": True,
            "properties": {
                "timestamp": {
                    "type": "date"
                },
                "foo": {
                    "type": "integer"
                },
                "bar": {
                    "type": "integer"
                },
                "baz": {
                    "type": "integer"
                },
                "tag_kw": {
                    "type": "keyword"
                },
                "tag_int": {
                    "type": "integer"
                },
                "tag_bool": {
                    "type": "boolean"
                },
            },
        },
    },
}

FEATURES = [
    {
        'name': 'avg_foo',
        'metric': 'avg',
        'field': 'foo',
        'default': 0,
    },
]

FEATURES_MATCH_ALL_TAG1 = [
    {
        'name': 'avg_baz',
        'metric': 'avg',
        'field': 'baz',
        'match_all': [
            {'tag': 'tag_kw', 'value': 'tag1'},
        ],
    },
]
FEATURES_MATCH_ALL_TAG2 = [
    {
        'name': 'avg_baz',
        'metric': 'avg',
        'field': 'baz',
        'match_all': [
            {'tag': 'tag_int', 'value': 7},
            {'tag': 'tag_bool', 'value': True},
        ],
    },
]

class TestElasticDataSource(unittest.TestCase):
    def setUp(self):
        bucket_interval = 3

        t0 = int(datetime.datetime.now().timestamp())
        t0 -= t0 % bucket_interval
        self.t0 = t0

        self.index = 'test-%d' % t0
        logging.info("creating index %s", self.index)
        self.source = ElasticsearchDataSource({
            'name': 'test',
            'addr': os.environ['ELASTICSEARCH_ADDR'],
            'index': self.index,
        })
        self.source.drop()
        self.source.init(template_name="test", template=TEMPLATE)

        self.model = TimeSeriesModel(dict(
            name='times-model', # not test-model due to TEMPLATE
            offset=30,
            span=300,
            bucket_interval=bucket_interval,
            interval=60,
            features=FEATURES,
            threshold=30,
        ))

        data = [
            # (foo, bar|baz, timestamp)
            (1, 33, t0 - 1), # excluded
            (2, 120, t0), (3, 312, t0 + 1),
            # empty
            (4, 18, t0 + 7),
            (5, 78, t0 + 9), # excluded
        ]
        for foo, bar, ts in data:
            self.source.insert_times_data(
                ts=ts,
                data={
                    'foo': foo,
                }
            )
            self.source.insert_times_data(
                ts=ts,
                data={
                    'bar': bar,
                }
            )
            self.source.insert_times_data(
                ts=ts,
                tags={
                    'tag_kw': 'tag1',
                    'tag_int': 9,
                    'tag_bool': False,
                },
                data={
                    'baz': bar,
                }
            )
            self.source.insert_times_data(
                ts=ts,
                tags={
                    'tag_kw': 'tag2',
                    'tag_int': 7,
                    'tag_bool': True,
                },
                data={
                    'baz': -bar,
                }
            )

        self.source.commit()

        # Let elasticsearch indexes the data before querying it
        time.sleep(10)

    def tearDown(self):
        self.source.drop()

    def test_get_index_name(self):
        ts = 1527156069

        self.assertEqual(self.source.get_index_name(), self.index)
        self.assertEqual(self.source.get_index_name("test"), "test")
        self.assertEqual(
            self.source.get_index_name("test", timestamp=ts),
            "test"
        )
        self.assertEqual(
            self.source.get_index_name("test-*", timestamp=ts),
            "test-2018.05.24",
        )

    def test_get_times_data(self):
        res = self.source.get_times_data(
            self.model,
            from_date=self.t0,
            to_date=self.t0 + 8,
        )

        foo_avg = []
        for line in res:
            foo_avg.append(line[1][0])

        np.testing.assert_allclose(
            np.array(foo_avg),
            np.array([2.5, np.nan, 4.0]),
            rtol=0,
            atol=0,
        )

    def test_save_timeseries_prediction(self):
        now_ts = datetime.datetime.now().timestamp()

        timestamps = [
            now_ts,
            now_ts + self.model.bucket_interval,
        ]
        predicted = [[4.0], [2.0]]

        prediction = TimeSeriesPrediction(
            self.model,
            timestamps=timestamps,
            predicted=np.array(predicted),
            observed=np.array([[4.1], [1.9]]),
        )

        self.source.drop(self.model.name)
        self.source.save_timeseries_prediction(prediction, self.model)
        self.source.refresh()

        res = self.source.search(
            index=self.model.name,
            routing=self.model.routing,
            size=100,
            body={}
        )

        hits = res['hits']['hits']
        self.assertEqual(len(hits), 2)

        for i, hit in enumerate(sorted(hits, key=lambda x: x['_source']['timestamp'])):
            source = hit['_source']
            self.assertEqual(source, {
                'avg_foo': predicted[i][0],
                'timestamp': int(timestamps[i] * 1000),
            })

    def test_match_all(self):
        model = TimeSeriesModel(dict(
            name="times-model",
            offset=30,
            span=300,
            bucket_interval=3,
            interval=60,
            features=FEATURES_MATCH_ALL_TAG1,
            threshold=30,
        ))
        res = self.source.get_times_data(
            model,
            from_date=self.t0,
            to_date=self.t0 + 8,
        )
        baz_avg = []
        for line in res:
            baz_avg.append(line[1][0])

        np.testing.assert_allclose(
            np.array(baz_avg),
            np.array([216.0, np.nan, 18.0]),
            rtol=0,
            atol=0,
        )

        model = TimeSeriesModel(dict(
            name="times-model",
            offset=30,
            span=300,
            bucket_interval=3,
            interval=60,
            features=FEATURES_MATCH_ALL_TAG2,
            threshold=30,
        ))

        res = self.source.get_times_data(
            model,
            from_date=self.t0,
            to_date=self.t0 + 8,
        )
        baz_avg = []
        for line in res:
            baz_avg.append(line[1][0])

        np.testing.assert_allclose(
            np.array(baz_avg),
            np.array([-216.0, np.nan, -18.0]),
            rtol=0,
            atol=0,
        )

VOIP_TEMPLATE = {
    "template": "test-voip-*",
    "mappings": {
        "session": {
            "properties": {
                "@timestamp": {
                    "type": "date"
                },
                "duration": {
                    "type": "integer"
                },
                "caller": {
                    "type": "keyword"
                },
                "international": {
                    "type": "boolean"
                },
                "toll_call": {
                    "type": "boolean"
                }
            }
        }
    }
}

class TestElasticFingerprints(loudml.test.TestFingerprints):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Let elasticsearch indexes the data before querying it
        time.sleep(10)

    def init_source(self):
        addr = os.environ.get('ELASTICSEARCH_ADDR', 'localhost:9200')
        self.index = 'test-voip-{}'.format(self.from_ts)
        logging.info("creating index %s", self.index)
        self.source = ElasticsearchDataSource({
            'name': 'test',
            'type': 'elasticsearch',
            'addr': addr,
            'index': self.index,
        })
        self.source.drop()
        self.source.init(template_name="test", template=TEMPLATE)

    def __del__(self):
        self.source.drop()
