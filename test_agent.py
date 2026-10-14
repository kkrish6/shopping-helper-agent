"""Offline tests use the real LangChain runtime and a scripted chat model.

They test orchestration, not real-provider intelligence or API compatibility.
"""
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agent import ShoppingSession, render_answer, run_shopping_agent
from providers import Product
from store import Store


class ScriptedModel(BaseChatModel):
    replies: list = Field(default_factory=list)
    bound_names: list = Field(default_factory=list)
    seen_tools: list = Field(default_factory=list)
    index: int = 0

    @property
    def _llm_type(self):
        return 'scripted-tool-test'

    def bind_tools(self, tools, **kwargs):
        self.bound_names = [t.name for t in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen_tools = [m.name for m in messages if m.type == 'tool']
        reply = self.replies[self.index]
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(name, args, id='c1'):
    return AIMessage(content='', tool_calls=[{'name': name, 'args': args, 'id': id}])


def memory_store():
    return Store(':memory:')


def test_no_key_fallback(monkeypatch):
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    result = run_shopping_agent('Compare earbuds under 1000', memory_store(), ['demo'])
    assert result['mode'] == 'rules'
    assert result['records'][0]['tool'] == 'compare_products'
    assert all(p['price'] <= 1000 for p in result['records'][0]['data']['products'])


def test_real_langchain_two_step_tool_loop():
    model = ScriptedModel(replies=[call('search_products', {'query': 'earbuds'}, '1'),
                                   call('compare_products', {'query': 'earbuds'}, '2'),
                                   AIMessage(content='Buy imaginary item for INR 1.00')])
    result = run_shopping_agent('Compare earbuds under 1000', memory_store(), ['demo'], model=model)
    assert result['mode'] == 'langchain'
    assert [r['tool'] for r in result['records']] == ['search_products', 'compare_products']
    assert set(model.bound_names) == {'search_products', 'compare_products', 'price_history'}
    assert model.seen_tools == ['search_products', 'compare_products']
    assert 'imaginary' not in render_answer(result)
    assert 'sample data' in render_answer(result)
    assert all(p['price'] <= 1000 for r in result['records'] for p in r['data']['products'])
    for p in result['records'][1]['data']['alternatives']:
        assert p['saving'] == round(result['records'][1]['data']['best_match']['price'] - p['price'], 2)


def test_history_is_read_only_and_runs_on_tool_thread():
    store = memory_store()
    wid = store.add_watch(Product('test', 1000, 'https://example.com/1', 'demo'))
    store.record_price(wid, 800)
    before = store.history(wid)
    model = ScriptedModel(replies=[call('price_history', {'watch_id': wid}), AIMessage(content='done')])
    result = run_shopping_agent(f'Price history watch {wid}', store, ['demo'], model=model)
    assert result['mode'] == 'langchain'
    assert result['records'][0]['data']['watches'][0]['stats']['latest'] == 800
    assert len(store.history(wid)) == len(before)
    assert 'not a live price check' in render_answer(result)


@pytest.mark.parametrize('text,tool', [('earbuds under 1000', 'search_products'),
                                     ('cheaper earbuds', 'compare_products'),
                                     ('history watch 99', 'price_history')])
def test_forced_rules(text, tool):
    assert run_shopping_agent(text, memory_store(), ['demo'], use_llm=False)['records'][0]['tool'] == tool


def test_model_failure_falls_back_without_exposing_secret():
    # Empty script throws an exception inside the actual LangChain graph.
    result = run_shopping_agent('earbuds', memory_store(), ['demo'], model=ScriptedModel())
    assert result['mode'] == 'rules'
    assert 'unavailable' in result['note']


def test_no_tool_response_not_accepted():
    model = ScriptedModel(replies=[AIMessage(content='Fake price INR 123')])
    result = run_shopping_agent('earbuds', memory_store(), ['demo'], model=model)
    assert result['mode'] == 'rules'
    assert 'Fake' not in render_answer(result)


def test_tool_limit_forces_fallback():
    model = ScriptedModel(replies=[call('search_products', {'query': 'earbuds'}, str(i)) for i in range(10)])
    result = run_shopping_agent('earbuds', memory_store(), ['demo'], model=model)
    assert result['mode'] == 'rules'
    assert len(result['records']) == 1


def test_no_sources_no_results():
    result = run_shopping_agent('earbuds under 0', memory_store(), [], use_llm=False)
    assert result['records'][0]['data']['products'] == []
    assert 'No listings' in render_answer(result)


def test_cache_and_schema_validation():
    session = ShoppingSession(memory_store(), ['demo'])
    tools = {t.name: t for t in session.tools()}
    tools['search_products'].invoke({'query': 'earbuds'})
    tools['compare_products'].invoke({'query': 'earbuds'})
    assert len(session.cache) == 1
    with pytest.raises(ValueError):
        tools['search_products'].invoke({'query': 'earbuds', 'max_price': -1})
    with pytest.raises(ValueError):
        tools['price_history'].invoke({'watch_id': 'not-an-int'})


@pytest.mark.parametrize('text', ['', ' '*5, 'a'*501])
def test_invalid_request(text):
    with pytest.raises(ValueError):
        run_shopping_agent(text, memory_store(), ['demo'])


def test_streamlit_agent_smoke(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('SHOPPER_DB', str(tmp_path / 'ui.db'))
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    app = AppTest.from_file('streamlit_app.py').run()
    assert not app.exception
    app.text_input(key='agent_query').input('Compare earbuds under 1000')
    next(b for b in app.button if b.label == 'Ask agent').click().run()
    assert not app.exception
    assert any('Mode: rules' in t.value for t in app.text)
    assert any('INR' in t.value for t in app.text)


def test_missing_langchain_still_uses_rules(monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == 'langchain.agents':
            raise ImportError('optional dependency unavailable')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    result = run_shopping_agent('earbuds', memory_store(), ['demo'], model=ScriptedModel())
    assert result['mode'] == 'rules'


@pytest.mark.parametrize('budget', [float('nan'), float('inf'), -1])
def test_invalid_numeric_budgets(budget):
    session = ShoppingSession(memory_store(), ['demo'])
    with pytest.raises(ValueError):
        session.execute('search_products', 'earbuds', budget)


def test_combined_history_search_multitool():
    model = ScriptedModel(replies=[AIMessage(content='', tool_calls=[
        {'name': 'price_history', 'args': {}, 'id': 'h'},
        {'name': 'search_products', 'args': {'query': 'earbuds'}, 'id': 's'}]), AIMessage(content='done')])
    result = run_shopping_agent('Show history and find earbuds under 1000', memory_store(), ['demo'], model=model)
    assert result['mode'] == 'langchain'
    assert {r['tool'] for r in result['records']} == {'price_history', 'search_products'}
