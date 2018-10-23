"""
Loud ML model
"""

import copy
import numpy as np

from voluptuous import (
    ALLOW_EXTRA,
    All,
    Any,
    Length,
    Match,
    Range,
    Required,
    Optional,
    Boolean,
    Schema,
)

from . import (
    errors,
    misc,
    schemas,
)

def _convert_features_dict(features):
    """
    Convert old features dict format to list
    """

    result = []

    for io, lst in features.items():
        for feature in lst:
            feature['io'] = io
            result.append(feature)

    return result

def flatten_features(features):
    """
    Normalize feature list to the current format
    """

    if isinstance(features, dict):
        features = _convert_features_dict(features)

    inout = []
    in_only = []
    out_only = []

    for feature in features:
        io = feature.get('io')

        if io == 'o':
            out_only.append(feature)
        elif io == 'i':
            in_only.append(feature)
        else:
            if io is None:
                feature['io'] = 'io'
            inout.append(feature)

    return inout + out_only + in_only


class Feature:
    """
    Model feature
    """

    SCHEMA = Schema({
        Required('name'): All(schemas.key, Length(max=256)),
        Required('metric'): All(schemas.key, Length(max=256)),
        Required('field'): All(schemas.dotted_key, Length(max=256)),
        'measurement': Any(None, schemas.dotted_key),
        'collection': Any(None, schemas.key),
        'match_all': Any(None, Schema([
            {Required(schemas.key): Any(
                int,
                bool,
                float,
                All(str, Length(max=256)),
            )},
        ])),
        'default': Any(None, int, float, 'previous'),
        Optional('io', default='io'): Any('io', 'o', 'i'),
        'script': Any(None, str),
        Optional('anomaly_type', default='low_high'): Any('low', 'high', 'low_high'),
        'transform': Any(None, "diff"),
        'scores': Any(None, "min_max", "normalize", "standardize"),
    })

    def __init__(
        self,
        name=None,
        metric=None,
        field=None,
        measurement=None,
        collection=None,
        match_all=None,
        default=None,
        script=None,
        anomaly_type='low_high',
        transform=None,
        scores=None,
        io='io',
    ):
        self.validate(locals())

        self.name = name
        self.metric = metric
        self.measurement = measurement
        self.collection = collection
        self.field = field
        self.default = np.nan if default is None else default
        self.script = script
        self.match_all = match_all
        self.anomaly_type = anomaly_type
        self.is_input = 'i' in io
        self.is_output = 'o' in io
        self.transform = transform
        self.scores = "min_max" if scores is None else scores

    @classmethod
    def validate(cls, args):
        del args['self']
        return schemas.validate(cls.SCHEMA, args)


class Model:
    """
    Loud ML model
    """

    TYPE = 'generic'
    SCHEMA = Schema({
        Required('name'): All(schemas.key, Length(max=256)),
        Required('type'): All(schemas.key, Length(max=256)),
        Optional('features'): Any(None,
            All([Feature.SCHEMA], Length(min=1)),
            Schema({
                Optional('i'): All([Feature.SCHEMA], Length(min=1)),
                Optional('o'): All([Feature.SCHEMA], Length(min=1)),
                Optional('io'): All([Feature.SCHEMA], Length(min=1)),
            }),
        ),
        'routing': Any(None, schemas.key),
        'threshold': schemas.score,
        'max_threshold': schemas.score,
        'min_threshold': schemas.score,
        'max_evals': All(int, Range(min=1)),
    }, extra=ALLOW_EXTRA)

    def __init__(self, settings, state=None):
        """
        name -- model settings
        """
        settings['type'] = self.TYPE
        settings = copy.deepcopy(settings)

        settings = self.validate(settings)
        self._settings = settings
        self.name = settings.get('name')
        self.routing = settings.get('routing')
        self._state = state

        features = flatten_features(settings.get('features'))
        settings['features'] = features

        self.features = [Feature(**feature) for feature in features]

        self.max_threshold = self.settings.get('max_threshold')
        if self.max_threshold is None:
            # Backward compatibility
            self.max_threshold = self.settings.get('threshold', 0)
            self.settings['max_threshold'] = self.max_threshold

        self.min_threshold = self.settings.get('min_threshold')
        if self.min_threshold is None:
            # Backward compatibility
            self.min_threshold = self.settings.get('threshold', 0)
            self.settings['min_threshold'] = self.min_threshold

    @classmethod
    def validate(cls, settings):
        """Validate the settings against the schema"""
        return schemas.validate(cls.SCHEMA, settings)

    @property
    def type(self):
        return self.settings['type']

    @property
    def default_datasource(self):
        return self._settings.get('default_datasource')

    @property
    def settings(self):
        return self._settings

    @property
    def nb_features(self):
        return len(self.features)

    @property
    def is_trained(self):
        return self._state is not None

    @property
    def data(self):
        return {
            'settings': self.settings,
            'state': self.state,
        }

    @property
    def seasonality(self):
        return self._settings['seasonality']

    @property
    def state(self):
        return self._state

    @property
    def preview(self):
        state = {
            'trained': self.is_trained,
        }

        if self.is_trained:
            state['loss'] = self.state.get('loss')

        return {
            'settings': self.settings,
            'state': state,
        }

    def generate_fake_prediction(self):
        """
        Generate a prediction with fake values. Just for testing purposes.
        """
        return NotImplemented()

def load_model(settings, state=None, config=None):
    """
    Load model

    :param settings: model settings
    :type  settings: dict

    :param state: model state
    :type  state: opaque type

    :param config: running configuration
    :type  config: loudml.Config
    """

    model_type = settings['type']

    if config and model_type not in config.limits['models']:
        raise errors.Forbidden("Not allowed by license: " + model_type)

    try:
        model_cls = misc.load_entry_point('loudml.models', model_type)
    except ImportError:
        raise errors.UnsupportedModel(model_type)

    if model_cls is None:
        raise errors.UnsupportedModel(model_type)
    return model_cls(settings, state)
