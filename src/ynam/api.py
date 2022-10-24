from dataclasses import dataclass
from datetime import datetime
import ast
import inspect
import requests, json
import mintapi
from .secrets import stash
from .parser import arg

tfmt = '%Y-%m-%d'


@dataclass
class MintTransaction:

    date: str
    amount: int
    inferredDescription: str
    id: str

    def asYNAB(self):
        nt = {}
        nt['date'] = self.date
        nt['amount'] = int(self.amount) * 1000
        nt['account_id'] = stash.account_id
        nt['payee_name'] = self.inferredDescription
        nt['import_id'] = self.id
        nt['cleared'] = "cleared"
        return YNABTransaction(**nt)

    @classmethod
    def from_dict(cls, env):
        return cls(**{
            k: v
            for k, v in env.items() if k in inspect.signature(cls).parameters
        })


@dataclass
class YNABTransaction:

    date: str
    amount: int
    account_id: str
    payee_name: str
    import_id: str

    def __dict__(self):
        return {"transaction": {dir(self)}}

    @classmethod
    def from_dict(cls, env):
        return cls(**{
            k: v
            for k, v in env.items() if k in inspect.signature(cls).parameters
        })


class MintAPI():

    def __init__(self) -> None:
        self.restClient = mintapi.RESTClient
        self.browser = mintapi.SeleniumBrowser
        self.cpath = arg('cookies')
        self.keypath = arg('key')

    def freshMints(self):
        client = self.restClient()
        key = self.key()
        cookies = self.cookies()

        client.authorize(cookies, key)
        try:
            items = client.get_transaction_data()
        except:
            self.updateAuth()
            client.authorize(cookies, key)
            items = client.get_transaction_data()
        finally:
            return recent(
                [MintTransaction.from_dict(item['fiData']) for item in items])

    def cookies(self):
        try:
            with open(self.cpath, 'r') as file:
                return ast.literal_eval(file.read())
        except FileNotFoundError:
            self.updateAuth()
            with open(self.cpath, 'r') as file:
                return ast.literal_eval(file.read())

    def key(self):
        try:
            with open(self.keypath, 'r') as file:
                return ast.literal_eval(file.read())['authorization']
        except FileNotFoundError:
            self.updateAuth()
            with open(self.keypath, 'r') as file:
                return ast.literal_eval(file.read())['authorization']

    def updateAuth(self):
        bowser = self.browser(
            email=stash.username,
            password=stash.password,
            mfa_method='soft-token',
            mfa_token=stash.mfa_seed_token,
            use_chromedriver_on_path=arg('use_chromedriver_on_path'),
            headless=arg('headless'),
            wait_for_sync=False,
            wait_for_sync_timeout=10,
        )
        with open(arg('cookies'), 'w+') as file:
            file.write(str(bowser._get_cookies()))

        with open(arg('key'), 'w+') as file:
            file.write(str(bowser._get_api_key_header()))


class YNABAPI():

    def __init__(self) -> None:
        self.uri = 'https://api.youneedabudget.com/v1/'
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {stash.api_key}"
        }

    def _post(self, url, **kwargs):
        return requests.post(self.uri + url, **kwargs, headers=self.headers)

    def _get(self, url, **kwargs):
        return requests.get(self.uri + url, **kwargs, headers=self.headers)

    def bulkPostTransactions(self, transactions: dict[YNABTransaction]):
        results = self._post(
            f'/budgets/{stash.budget_id}/transactions',
            json={"transactions": transactions},
        )

        return real(results)

    def getTransactions(self, since_date: str = '', type: str = ''):
        """
        Return all recent transactions
        """
        result = self._get(
            f'/budgets/{stash.budget_id}/transactions',
            json={"data": {
                "since_date": since_date,
                "type": type,
            }},
        )

        return recent([
            YNABTransaction.from_dict(xt)
            for xt in real(result)['transactions']
        ])

    def getAccounts(self):
        """
        Return list of bank accounts/cards linked to default budget
        """
        return real(
            self._get(f'/budgets/{stash.budget_id}/accounts'))['accounts']

    def getBudgets(self):
        """
        Return list of budgets
        """
        return real(self._get(url='/budgets'))['budgets']


def recent(transactions) -> dict:
    filter = lambda xtDate: xtDate >= str(arg('days'))
    return [
        xt for xt in transactions
        if filter(datetime.strptime(xt.date, tfmt).strftime(tfmt))
    ]


def real(httpResponse) -> dict:
    answer = json.loads(httpResponse.content.decode('utf-8'))
    try:
        return answer['data']
    except Exception as e:
        print(answer)
        raise e