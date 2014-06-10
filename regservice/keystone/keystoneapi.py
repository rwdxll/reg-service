
import settings
import uuid
import keystoneclient
from keystoneclient.v3 import client
from datetime import datetime
from neutronclient.v2_0 import client as neutron_client
import logging as log
from flask import current_app
import copy


API_VERSION_V2 = "v2.0"
settings._public_data["api_v2_version"] = API_VERSION_V2
KEYSTONE_PUBLIC_V2_ENDPOINT = settings.KEYSTONE_PUBLIC_ENDPOINT
KEYSTONE_PUBLIC_V2_ENDPOINT = KEYSTONE_PUBLIC_V2_ENDPOINT.replace('v3','v2.0')

def write_log(data):
    f=open("/tmp/custom.log","a")
    f.write(data)
    f.close()	
		

def get_client():
    """
    """
    keystone = client.Client(token=settings.KEYSTONE_ADMIN_TOKEN, 
                    endpoint=settings.KEYSTONE_ADMIN_ENDPOINT)
    return keystone

def get_neutron_client(uname,pwd,tenantname):
    """                 
    """                 
    try:
        neutron = neutron_client.Client(username=uname,password=pwd,auth_url=KEYSTONE_PUBLIC_V2_ENDPOINT,tenant_name=tenantname)
        neutron.format= 'json'
    except Exception as e:
        current_app.logger.exception("Exception in neutron client")
        current_app.logger.exception(e)
    #neutron = neutron_client.Client(token=settings.KEYSTONE_ADMIN_TOKEN,auth_url=settings.KEYSTONE_PUBLIC_V2_ENDPOINT,tenant_name=tenantname)
    return neutron

def _create_user(name, domain=None, project=None, password=None,
                        email=None, description=None, enabled=None,
                        default_project=None, keystone=None, 
                        **kwargs):
    """
    """
    if not keystone:
        keystone = get_client()
    user = keystone.users.create(name, domain=None, project=None, password=password, 
            email=email, description=None, enabled=enabled, default_project=None,
            **kwargs)
    return user


def create_user(name, password, email=None, description=None, enabled=False, **kwargs):
    """
    """
    project = None
    user = None
    network = None
    role_granted = False
    neutron = None 
    keystone = get_client()
    _user = get_user_by_name(name)
    if _user:
        raise keystoneclient.apiclient.exceptions.Conflict("User already exist")
    try:
        domain = get_default_domain(keystone) 
        tenant_name = name + '-' + datetime.now().strftime('%Y%m%d%H%M%S')
        project = create_project(domain, tenant_name , keystone)
        role = get_default_role(keystone)
        ##SM:domain is optional
        user = _create_user(name, domain=domain, project=project, password=password, 
            email=email, enabled=enabled, keystone=keystone, **kwargs)
        ##SM:Specify either a domain or project, not both
        keystone.roles.grant(role, user=user, domain=None, project=project)
        role_granted = True
        user = keystone.users.update(user=user.id,enabled=True)
        try:
            neutron = get_neutron_client(name,password,tenant_name)
        except Exception as e:
            log.exception("Exception while initializing neutron client")
            current_app.logger.exception(e)
        try:
            if neutron:
                network = create_network(neutron,domain.name)
        except Exception as e:
            current_app.logger.exception(e)
            log.exception("Exception while creating network %s"%(str(e)))
        user = keystone.users.update(user=user.id,enabled=False)
    except Exception as ex:
        if role_granted:
            keystone.roles.revoke(role, user=user, domain=None, project=project)
        if user:
            delete_user(user)
        if project:
            delete_project(project)
        if network:
            delete_network(neutron,network)
        raise ex
    return user


def delete_user(id, keystone=None):
    if not keystone:
        keystone = get_client()
    keystone.users.delete(id)


def create_project(domain, name=None, keystone=None):
    """
    """
    project = None
    if not name:
        name = get_unique_project_name()
    if not keystone:
        keystone = get_client()
    project = keystone.projects.create(name, domain)
    return project

def create_network(neutron,network_name):
    """
    """
    try:
        body_sample = {'network': {'name': network_name, 'admin_state_up': True}}
        network = neutron.create_network(body=body_sample)
        return network
    except Exception as e:
        current_app.logger.exception(e)
        current_app.logger.exception("Exception was raised while creating neutron network")

def delete_project(id, keystone=None):
    if not keystone:
        keystone = get_client()
    keystone.projects.delete(id)

def delete_network(neutron,network):
    try:
        neutron.delete_network(network["network"]["id"])
    except Exception as e:
        current_app.logger.exception("Exception while deleting network")
        current_app.logger.exception(e)
    

def get_unique_project_name():
    """
    """
    project_name = settings.PROJECT_NAME_PREFIX + uuid.uuid4().hex
    while  True:
        project = get_project_by_name(name=project_name)
        if not project:
            break
        project_name = settings.PROJECT_NAME_PREFIX + uuid.uuid4().hex
    return project_name


def get_user_by_name(name, keystone=None):
    user = None
    if not keystone:
        keystone = get_client()
    user_list = keystone.users.list(name=name)
    if user_list:
        user = user_list[0]
    return user


def get_user(id, keystone=None):
    user = None
    if not keystone:
        keystone = get_client()
    user = keystone.users.get(id)
    return user


def get_project_by_name(name=None, project_id=None, keystone=None):
    project = None
    if not keystone:
        keystone = get_client()
    project_list = keystone.projects.list(name=name)
    if project_list:
        project = project_list[0]
    return project

        
def get_default_role(keystone=None):
    role = None
    if not keystone:        
        keystone = get_client()
    role_list = keystone.roles.list(name=settings.DEFAULT_ROLE_NAME)
    if not role_list:
        raise Exception("Could not find the default role:%s"%(settings.DEFAULT_ROLE_NAME))
    else:
        return role_list[0]


def get_default_domain(keystone=None):
    """
    """
    domain = None
    if not keystone:
        keystone = get_client()
    domain = [x for x in keystone.domains.list() if x.name in [settings.DEFAULT_DOMAIN_NAME]]
    if not domain:
        raise Exception("Could not find the default domain:%s"%(settings.DEFAULT_DOMAIN_NAME))
    else:
        return domain[0]


def enable_user(user_id, keystone=None):
    """
    """
    if not keystone:
        keystone = get_client()
    user = keystone.users.update(user=user_id, enabled=True,
            sms_activation_code=None, sms_activation_code_time=None)    
    return user


def update_user(user, **data):
    keystone = get_client()
    manager = keystone.users

    # v3 API is so much simpler...
    user = manager.update(user, **data)

    return user


