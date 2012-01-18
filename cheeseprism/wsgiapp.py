from cheeseprism.auth import BasicAuthenticationPolicy
from cheeseprism.request import CPRequest as Request
from cheeseprism.resources import get_root
from pyramid.config import Configurator
from pyramid.session import UnencryptedCookieSessionFactoryConfig
from pyramid_jinja2 import renderer_factory


def main(global_config, **settings):
    settings.setdefault('jinja2.i18n.domain', 'CheesePrism')
    session_factory = UnencryptedCookieSessionFactoryConfig('cheeseprism')
    policy = BasicAuthenticationPolicy(BasicAuthenticationPolicy.noop_check)

    config = Configurator(
        root_factory=get_root,
        settings=settings,
        session_factory=session_factory,
        authentication_policy=policy,
        )
    
    config.add_translation_dirs('locale/')
    config.include('pyramid_jinja2')
    config.add_renderer('.html', renderer_factory)

    config.add_static_view('static', 'static')
    config.scan('cheeseprism.views')
    config.scan('cheeseprism.index')
    config.set_request_factory(Request)
    config.add_route('package', 'package/{name}/{version}')

    return config.make_wsgi_app()
