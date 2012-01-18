from cheeseprism import event
from cheeseprism import pipext
from cheeseprism import resources
from cheeseprism import utils
from cheeseprism.rpc import PyPi
from cheeseprism.resources import Root
from path import path
from pyramid.httpexceptions import HTTPFound
from pyramid.i18n import TranslationStringFactory
from pyramid.view import view_config
from pyramid.events import (
    BeforeRender,
    subscriber,
    )
from pyramid.traversal import find_interface
from urllib2 import HTTPError
from urllib2 import URLError
from webob import exc
import logging
import requests
import tempfile


logger = logging.getLogger(__name__)


_ = TranslationStringFactory('CheesePrism')

@subscriber(BeforeRender)
def before_render(event):
    request = event['request']
    context = event['context']
    event['ctx_url'] = request.resource_url(context)
    event['app_url'] = request.application_url
    
@view_config(renderer='root.html', context=resources.Root)
def homepage(context, request):
    return {}

@view_config(name='indexes', renderer='indexes.html', context=resources.Root,
             request_method='GET')
def show_indexes(context, request):
    indexes = context.indexes()
    return {'indexes':indexes}

@view_config(name='indexes', renderer='indexes.html', context=resources.Root,
             request_method='POST')
def add_index(context, request):
    index_name = request.POST['name']
    context.add_index(index_name)
    request.session.flash('Index %s added' % index_name)
    return HTTPFound(location=request.resource_url(context, '@@indexes'))

@view_config(
    name='instructions', renderer='instructions.html', context=resources.Index)
def instructions(context, request):
    return {'page': 'instructions'}

@view_config(renderer='index.html', context=resources.Index)
def index(context, request):
    packages = context.packages()
    return {'packages':packages}

@view_config(name='simple', context=resources.Index, request_method='POST')
def upload(context, request):
    """
    The interface for distutils upload
    """
    content = request.POST['content']
    if not hasattr(content, 'file'):
        raise RuntimeError('No file attached') 

    fn = utils.secure_filename(content.filename)
    context.write_distribution_file(fn, content.file)
    context.manager.update_by_request(request)
    request.response.headers['X-Swalow-Status'] = 'SUCCESS'
    return request.response

@view_config(name='find-packages', renderer='find_packages.html',
             context=resources.Index)
def find_package(context, request):
    releases = None
    search_term = None
    if request.method == "POST":
        search_term = request.POST['search_box']
        releases = PyPi.search(search_term)
    url = request.resource_url(context, request.view_name)
    return dict(releases=releases, search_term=search_term, here=url)

@view_config(name='package', context=resources.Index)
def package(context, request):
    """
    @@ convert to use action on a post rather than on a get
    """
    subpath = request.subpath
    name, version = subpath[:2]
    details = PyPi.package_details(name, version)
    flash = request.session.flash 
    if not details:
        flash("%s-%s not found" %(name, version))
        return HTTPFound(request.resource_url(context, '@@find-packages'))

    root = find_interface(context, Root)

    if details[0]['md5_digest'] in root.distribution_data:
        logger.debug('Package %s-%s already in index' %(name, version))
        return HTTPFound(location=request.resource_url(context))
            
    details = details[0]
    url = details['url']
    filename = details['filename']
    newfile = None
    try:
        resp = requests.get(url)
        newfile = root.path / filename
        root.write_distribution_file(newfile, resp.raw)
    except HTTPError, e:
        error = "HTTP Error: %d %s - %s" % (
            e.code, exc.status_map[e.code].title, url)
        logger.error(error)
        flash(error)
    except URLError, e:
        logger.error("URL Error: %s, %s", e.reason , url)
        flash('Url error attempting to grab %s: %s' %(url, e.reason))

    if newfile is not None:
        try:
            added_event = event.PackageAdded(context.manager, path=newfile)
            request.registry.notify(added_event)            
            flash('%s-%s was installed into the index successfully.' %
                  (name, version))
            return HTTPFound(location=request.resource_url(context, name))
        except Exception, e:
            flash('Issue with adding %s to index: See logs: %s' %
                  (newfile.name, e))

    return HTTPFound(location=request.resource_url(context, '@@find-packages'))


@view_config(name='regenerate', renderer='regenerate.html',
             context=resources.Index)
def regenerate_index(context, request):
    if request.method == 'POST':
        logger.debug("Regenerate index")
        homefile, leaves = context.manager.regenerate_all()
        logger.debug("regeneration done:\n %s %s", homefile, leaves) #@@ time it 
        return HTTPFound(location=request.resource_url(context))
    return {}


@view_config(name='load-requirements', renderer='requirements_upload.html', context=resources.Index)
def from_requirements(context, request):
    if request.method == "POST":
        req_text = request.POST['req_file'].file.read()
        index = request.index

        filename = path(tempfile.gettempdir()) / 'temp-req.txt'
        filename.write_text(req_text)
        names = []
        requirement_set, finder = pipext.RequirementDownloader.req_set_from_file(filename, request.file_root)
        downloader = pipext.RequirementDownloader(requirement_set, finder, seen=set(request.index_data))
        for pkginfo, outfile in downloader.download_all():
            name = pkginfo.name
            names.append(name)

        index.update_by_request(request)
        flash = request.sesion.flash
        if names:
            flash('The following packages were installed from the requirements file: %s' % ", ".join(names))

        if downloader.skip:
            for dl in (x.filename for x in downloader.skip):
                flash("Skipped (already in index): %s" %dl)

        if downloader.errors:
            for error in downloader.errors:
                flash('Download issue: %s' %error)
        
        return HTTPFound('/load-requirements')
    return {}

