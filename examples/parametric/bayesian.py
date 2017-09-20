from sklearn.ensemble import RandomForestRegressor
from sklearn.datasets.base import load_boston

from skpro.parametric import ParamtericEstimator
from skpro.parametric.estimators import Constant
from skpro.metrics import log_loss
from skpro.parametric.bayesian import BayesianLinearRegression
from skpro.workflow.manager import DataManager
from skpro.workflow.table import Table, IdModifier, SortModifier
from skpro.workflow.cross_validation import CrossValidationController, CrossValidationView
from skpro.workflow import Model
from skpro.workflow.utils import InfoView, InfoController


X, y = load_boston(return_X_y=True)
data = DataManager(X, y, name='Boston')

tbl = Table()

# Adding controllers displayed as columns
tbl.add(InfoController(), InfoView())

tbl.add(
    controller=CrossValidationController(data, loss_func=log_loss),
    view=CrossValidationView()
)

# Sort by score in the last column, i.e. log_loss
tbl.modify(SortModifier(key=lambda x: x[-1]['data']['score']))
# Use ID modifier to display model numbers
tbl.modify(IdModifier())

# Compose the models displayed as rows
models = [
    Model(ParamtericEstimator(point=RandomForestRegressor(), std=Constant('mean(y)'))),
    Model(ParamtericEstimator(point_std=BayesianLinearRegression()))
]

tbl.print(models)