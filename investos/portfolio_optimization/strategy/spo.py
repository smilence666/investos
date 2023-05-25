import pandas as pd
import datetime as dt
import cvxpy as cvx

from investos.portfolio_optimization.constraint_model import BaseConstraint, MaxWeightConstraint, MinWeightConstraint, MaxLeverageConstraint
from investos.portfolio_optimization.strategy import BaseStrategy
from investos.portfolio_optimization.cost_model import TradingCost, HoldingCost, BaseCost
from investos.util import values_in_time

class SPO(BaseStrategy):
    """Optimization strategy that builds trade list using single period optimization.

    Attributes
    ----------
    TBU
    """

    
    def __init__(self, 
                costs: [BaseCost] = [], 
                constraints: [BaseConstraint] = [MaxWeightConstraint(), MinWeightConstraint(), MaxLeverageConstraint()], 
                solver=None,
                solver_opts=None):
        self.forecast_returns = None # Set by Backtester in init
        self.optimizer = None # Set by Backtester in init

        self.costs = costs
        self.constraints = constraints
        self.solver = solver
        self.solver_opts = solver_opts or {}

    
    def generate_trade_list(self, holdings: pd.Series, t: dt.datetime) -> pd.Series:
        """Calculates and returns trade list (in units of currency passed in) using convex (single period) optimization.

        Parameters
        ----------
        holdings : pandas.Series
            Holdings at beginning of period `t`.
        t : datetime.datetime
            The datetime for associated holdings `holdings`.
        """

        if t is None:
            t = dt.datetime.today()

        value = sum(holdings)
        w = holdings / value # Portfolio weights
        z = cvx.Variable(w.size)  # Portfolio trades
        wplus = w.values + z # Portfolio weights after trades

        alpha_term = cvx.sum(cvx.multiply(
            values_in_time(self.forecast_returns, t).values,
            wplus))

        assert(alpha_term.is_concave())

        costs, constraints = [], []

        for cost in self.costs:
            cost_expr, const_expr = cost.weight_expr(t, wplus, z, value)
            costs.append(cost_expr)
            constraints += const_expr

        constraints += [item for item in (con.weight_expr(t, wplus, z, value)
                                          for con in self.constraints)]

        for el in costs:
            assert (el.is_convex())

        for el in constraints:
            assert (el.is_dcp())

        self.prob = cvx.Problem(
            # cvx.Maximize(alpha_term - sum(costs)),
            cvx.Maximize(alpha_term),
            [cvx.sum(z) == 0] + constraints) # Trades need to 0 out, i.e. cash account must adjust to make everything net to 0
        
        try:
            self.prob.solve(solver=self.solver, **self.solver_opts)

            if self.prob.status == 'unbounded':
                print(f"The problem is unbounded at {t}")
                return self._zerotrade(holdings)

            if self.prob.status == 'infeasible':
                raise Exception(
                    'The problem is infeasible')

            return pd.Series(index=holdings.index, data=(z.value * value))
        
        except (cvx.SolverError, TypeError):
            raise Exception(
                'The solver %s failed' % self.solver)
