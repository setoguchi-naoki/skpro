"""Cyclic boosting regressors.
This is a interface for Cyclic boosting, it contains efficient,
off-the-shelf, general-purpose supervised machine learning methods
for both regression and classification tasks.
Please read the official document for its detail
https://cyclic-boosting.readthedocs.io/en/latest/
"""
# copyright: skpro developers, BSD-3-Clause License (see LICENSE file)

__author__ = [
    "setoguchi-naoki"
]  # interface only. Cyclic boosting authors in cyclic_boosting package

import warnings
import numpy as np
import pandas as pd
from skpro.regression.base import BaseProbaRegressor
from skpro.distributions.qpd import QPD_S

# from cyclic_boosting import common_smoothers, binning
from cyclic_boosting import (
    pipeline_CBMultiplicativeQuantileRegressor,
    pipeline_CBAdditiveQuantileRegressor,
)


# todo: change class name and write docstring
class CyclicBoosting(BaseProbaRegressor):
    """Cyclic boosting regressor.

    Estimates the parameters of Johnson Quantile-Parameterized Distributions
    (JQPD) by quantile regression, which is one of the Cyclic boosting's functions
    this method can more accurately approximate to the distribution of observed data

    Parameters
    ----------
    feature_properties : dict
        name and characteristic of train dataset
        it is able to set multiple characteristic by OR operator
        e.g. {sample1: IS_CONTINUOUS | IS_LINEAR, sample2: IS_ORDERED}
        for basic options, see
        https://cyclic-boosting.readthedocs.io/en/latest/tutorial.html#set-feature-properties
    interaction : list[tuple], default=(), optional
        some combinations of explanatory variables, (interaction term)
        e.g. [(sample1, sample2), (sample1, sample3)]
    alpha : float, default=0.2
        lower quantile for QPD's parameter alpha
    mode : str, default='multiplicative'
        the type of quantile regressor. 'multiplicative' or 'additive'

    Attributes
    ----------
    estimators_ : list of of skpro regressors
        clones of regressor in `estimator` fitted in the ensemble
    quantiles : list, default=[0.2, 0.5, 0.8]
        targets of quantile prediction for j-qpd's param
    quantile_values: list
        quantile prediction results
    quantile_est: list
        estimators, each estimator predicts point in the value of quantiles attribute
    qpd: skpro.distributions.J_QPD_S
        Johnson Quantile-Parameterized Distributions instance

    Examples
    --------
    >>> from skpro.regression.cyclic_boosting import CyclicBoosting
    >>> from cyclic_boosting import flags
    >>> from sklearn.datasets import load_diabetes
    >>> from sklearn.model_selection import train_test_split
    >>> X, y = load_diabetes(return_X_y=True, as_frame=True)
    >>> X_train, X_test, y_train, y_test = train_test_split(X, y)
    >>>
    >>> fp = {
    >>>     'age': flags.IS_CONTINUOUS,
    >>>     'sex': flags.IS_CONTINUOUS,
    >>>     'bmi': flags.IS_CONTINUOUS,
    >>>     'bp':  flags.IS_CONTINUOUS,
    >>>     's1':  flags.IS_CONTINUOUS,
    >>>     's2':  flags.IS_CONTINUOUS,
    >>>     's3':  flags.IS_CONTINUOUS,
    >>>     's4':  flags.IS_CONTINUOUS,
    >>>     's5':  flags.IS_CONTINUOUS,
    >>>     's6':  flags.IS_CONTINUOUS,
    >>> }
    >>> reg_proba = CyclicBoosting(feature_properties=fp)
    >>> reg_proba.fit(X_train, y_train)
    >>> y_pred = reg_proba.predict_proba(X_test)
    """

    _tags = {
        "object_type": "regressor",
        "estimator_type": "regressor_proba",
        "capability:multioutput": False,
        "capability:missing": True,
        "X_inner_mtype": "pd_DataFrame_Table",
        "y_inner_mtype": "pd_DataFrame_Table",
        "python_dependencies": "cyclic_boosting>=1.2.1",
    }

    def __init__(
        self,
        feature_properties,
        interaction=tuple(),
        alpha=0.2,
        mode="multiplicative",
    ):
        self.feature_properties = feature_properties
        self.interaction = interaction
        self.alpha = alpha
        self.quantiles = [self.alpha, 0.5, 1 - self.alpha]
        self.quantile_values = []
        self.quantile_est = []
        self.qpd = None
        self.mode = mode

        super().__init__()

        # check parameters
        if not isinstance(feature_properties, dict):
            raise ValueError("feature_properties must be dict")
        for i in interaction:
            if not isinstance(i, tuple):
                raise ValueError("interaction must be tuple")
        if alpha >= 0.5 or alpha <= 0.0:
            raise ValueError("alpha's range must be 0.0 < alpha < 0.5")

        # build estimators
        features = list(self.feature_properties.keys())
        for i in interaction:
            features.append(i)

        if self.mode == "multiplicative":
            regressor = pipeline_CBMultiplicativeQuantileRegressor
        elif self.mode == "additive":
            regressor = pipeline_CBAdditiveQuantileRegressor
        else:
            raise ValueError("mode must be 'multiplicative' or 'additive'")

        for quantile in self.quantiles:
            self.quantile_est.append(
                regressor(
                    quantile=quantile,
                    feature_properties=self.feature_properties,
                    feature_groups=features,
                    maximal_iterations=50,
                )
            )

    def _fit(self, X, y):
        """Fit regressor to training data.

        Writes to self:
            Sets fitted model attributes ending in "_".

        Parameters
        ----------
        X : pandas DataFrame
            feature instances to fit regressor to
        y : pandas DataFrame, must be same length as X
            labels to fit regressor to

        Returns
        -------
        self : reference to self
        """

        self._y_cols = y.columns
        y = y.to_numpy().flatten()

        # multiple quantile regression for full probability estimation
        for est in self.quantile_est:
            est.fit(X.copy(), y)

        return self

    def _predict(self, X):
        """Predict median.

        State required:
            Requires state to be "fitted" = self.is_fitted=True

        Accesses in self:
            Fitted model attributes ending in "_"

        Parameters
        ----------
        X : pandas DataFrame, must have same columns as X in `fit`
            data to predict labels for

        Returns
        -------
        y : pandas DataFrame, same length as `X`, same columns as `y` in `fit`
            labels predicted for `X`
        """

        index = X.index
        y_cols = self._y_cols

        # median prediction
        median_estimator = self.quantile_est[1]
        yhat = median_estimator.predict(X.copy())

        y_pred = pd.DataFrame(yhat, index=index, columns=y_cols)
        return y_pred

    def _predict_proba(self, X):
        """Predict QPD from three predicted quantile values.

        State required:
            Requires state to be "fitted".

        Accesses in self:
            Fitted model attributes ending in "_"

        Parameters
        ----------
        X : pandas DataFrame, must have same columns as X in `fit`
            data to predict labels for

        Returns
        -------
        y_pred : skpro BaseDistribution, same length as `X`
            labels predicted for `X`
        """

        index = X.index
        y_cols = self._y_cols

        # predict quantiles
        self.quantile_values = []
        for est in self.quantile_est:
            yhat = est.predict(X.copy())
            self.quantile_values.append(yhat)

        # Johnson Quantile-Parameterized Distributions
        qpd = QPD_S(
            alpha=self.alpha,
            qv_low=self.quantile_values[0],
            qv_median=self.quantile_values[1],
            qv_high=self.quantile_values[2],
            index=index,
            columns=y_cols,
        )

        return qpd

    def _predict_interval(self, X, coverage):
        """Compute/return interval predictions.

        private _predict_interval containing the core logic,
            called from predict_interval and default _predict_quantiles

        Parameters
        ----------
        X : pandas DataFrame, must have same columns as X in `fit`
            data to predict labels for
        coverage : guaranteed list of float of unique values
           nominal coverage(s) of predictive interval(s)

        Returns
        -------
        pred_int : pd.DataFrame
            Column has multi-index: first level is variable name from ``y`` in fit,
            second level coverage fractions for which intervals were computed,
            in the same order as in input `coverage`.
            Third level is string "lower" or "upper", for lower/upper interval end.
            Row index is equal to row index of ``X``.
            Entries are lower/upper bounds of interval predictions,
            for var in col index, at nominal coverage in second col index,
            lower/upper depending on third col index, for the row index.
            Upper/lower interval end are equivalent to
            quantile predictions at alpha = 0.5 - c/2, 0.5 + c/2 for c in coverage.
        """

        index = X.index
        y_cols = self._y_cols
        columns = pd.MultiIndex.from_product(
            [y_cols, coverage, ["lower", "upper"]],
        )

        # predict interval
        interval = pd.DataFrame(index=index)
        for c in coverage:
            alpha = [0.5 - 0.5 * float(c), 0.5 + 0.5 * float(c)]
            interval = pd.concat(
                [interval, self.predict_quantiles(X=X.copy(), alpha=alpha)], axis=1
            )
        interval.columns = columns

        return interval

    def _predict_quantiles(self, X, alpha):
        """Compute/return quantile predictions.

        private _predict_quantiles containing the core logic,
            called from predict_quantiles and default _predict_interval

        Parameters
        ----------
        X : pandas DataFrame, must have same columns as X in `fit`
            data to predict labels for
        alpha : guaranteed list of float
            A list of probabilities at which quantile predictions are computed.

        Returns
        -------
        quantiles : pd.DataFrame
            Column has multi-index: first level is variable name from ``y`` in fit,
                second level being the values of alpha passed to the function.
            Row index is equal to row index of ``X``.
            Entries are quantile predictions, for var in col index,
                at quantile probability in second col index, for the row index.
        """

        is_given_proba = False
        warning = (
            "{} percentile doesn't trained, return QPD's quantile value, "
            "which is given by predict_proba(), "
            "if you need more plausible quantile value, "
            "please train regressor again for specified quantile estimation"
        )
        if isinstance(alpha, list):
            for a in alpha:
                if not (a in self.quantiles):
                    warnings.warn(warning.format(a))
                    is_given_proba = True
        elif isinstance(alpha, float):
            if not (alpha in self.quantiles):
                warnings.warn(warning.format(alpha))
                is_given_proba = True
        else:
            raise ValueError("alpha must be float or list of floats")

        index = X.index
        y_cols = self._y_cols

        columns = pd.MultiIndex.from_product(
            [y_cols, alpha],
        )

        # predict quantiles
        self.quantile_values = []
        if is_given_proba:
            qpd = self.predict_proba(X.copy())
            if isinstance(alpha, list):
                alpha = [alpha]

            p = pd.DataFrame(alpha, index=X.index, columns=columns)
            quantiles = qpd.ppf(p)

        else:
            for est in self.quantile_est:
                yhat = est.predict(X.copy())
                self.quantile_values.append(yhat)

            quantiles = pd.DataFrame(
                np.transpose(self.quantile_values), index=index, columns=columns
            )

        return quantiles

    @classmethod
    def get_test_params(cls, parameter_set="default"):
        """Return testing parameter settings for the estimator.

        Parameters
        ----------
        parameter_set : str, default="default"
            Name of the set of test parameters to return, for use in tests. If no
            special parameters are defined for a value, will return `"default"` set.

        Returns
        -------
        params : dict or list of dict, default = {}
            Parameters to create testing instances of the class
            Each dict are parameters to construct an "interesting" test instance, i.e.,
            `MyClass(**params)` or `MyClass(**params[i])` creates a valid test instance.
            `create_test_instance` uses the first (or only) dictionary in `params`
        """
        from cyclic_boosting import flags

        # NOTE: This test is only corresponded diabeat dataset
        fp = {
            "age": flags.IS_CONTINUOUS,
            "sex": flags.IS_CONTINUOUS,
            "bmi": flags.IS_CONTINUOUS,
            "bp": flags.IS_CONTINUOUS,
            "s1": flags.IS_CONTINUOUS,
            "s2": flags.IS_CONTINUOUS,
            "s3": flags.IS_CONTINUOUS,
            "s4": flags.IS_CONTINUOUS,
            "s5": flags.IS_CONTINUOUS,
            "s6": flags.IS_CONTINUOUS,
        }
        param1 = {"feature_properties": fp}
        param2 = {"feature_properties": fp, "interaction": [("age", "sex"), ("s1, s3")]}
        param3 = {
            "feature_properties": fp,
            "interaction": [("age", "sex")],
            "alpha": 0.3,
        }
        param4 = {
            "feature_properties": fp,
            "interaction": [("age", "sex")],
            "alpha": 0.3,
            "mode": "additive",
        }

        return [param1, param2, param3, param4]
