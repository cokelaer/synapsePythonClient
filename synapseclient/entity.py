##
## Represent a synapse entity
## chris.bare@sagebase.org
############################################################
import collections
import itertools
from dict_object import DictObject
from utils import id_of, entity_type, itersubclasses
import os


## File, Locationable and Summary are Versionable
class Versionable(object):
    _synapse_class = 'org.sagebionetworks.repo.model.Versionable'
    _property_keys = ['versionNumber', 'versionLabel', 'versionComment', 'versionUrl', 'versions']


## The Entity class is the base class for all entities. It has a few
## special characteristics. It is a dictionary-like object in which
## either object or dictionary notation (entity.foo or entity['foo'])
## can be used interchangeably.

## In Synapse, entities have both properties and annotations. This has
## come to be viewed as awkward, so we try to hide it. Furthermore,
## because we're getting tricky with the dot notation, there are three
## distinct namespaces to consider when accessing variables that are
## part of the entity: the members of the object, properties defined by
## Synapse, and Synapse annotations, which are open-ended and user-
## defined.

## The rule, for either getting or setting is: first look in the object
## then look in properties, then look in annotations. If the key is not
## found in any of these three, a get results in a KeyError and a set
## results in a new annotation being created. Thus, the following results
## in a new annotation that will be persisted in Synapse:
##   entity.foo = 'bar'

## To create an object member variable, which will *not* be persisted in
## Synapse, this unfortunate notation is required:
##   entity.__dict__['foo'] = 'bar'

## Between the three namespaces, name collisions are entirely possible,
## and already present in at least one instance - the 'annoations'
## property and the 'annotations' member variable that refers to the
## annotations dictionary. Keys in the three namespaces can be referred
## to unambiguously like so:
##   entity.__dict__['key']
##   entity.properties.key / entity.properties['key']
##   entity.annotations.key / entity.annotations['key']

## Alternate implementations include:
##  * a naming convention to tag object members
##  * keeping a list of 'transient' variables (the object members)
##  * giving up on the dot notation (implemented in Entity2.py in commit e441fcf5a6963118bcf2b5286c67fc66c004f2b5 in the entity_object branch)
##  * giving up on hiding the difference between properties and annotations

class Entity(collections.MutableMapping):
    """
    A Synapse entity is an object that has metadata, access control, and
    potentially a file. It can represent data, source code, or a folder
    that contains other entities.
    """

    _synapse_class = 'org.sagebionetworks.repo.model.Entity'
    _property_keys = ['id', 'name', 'description', 'parentId',
                     'entityType', 'concreteType',
                     'uri', 'etag', 'annotations', 'accessControlList',
                     'createdOn', 'createdBy', 'modifiedOn', 'modifiedBy']

    @classmethod
    def create(cls, properties=None, annotations=None):
        """
        Create an Entity or a subclass given dictionaries of properties
        and annotations, as might be received from the Synapse Repository.

        If entityType is defined in properties, we create the proper subclass
        of Entity. If not, give back the type asked for.

        If passed an Entity as input, create a new Entity using the input
        entity as a prototype.
        """
        ## create a new Entity using an existing entity as a prototype?
        if isinstance(properties, Entity):
            annotations = properties.annotations + annotations
            properties = properties.properties
            del properties['id']
        if cls==Entity and 'entityType' in properties and properties['entityType'] in _entity_type_to_class:
            cls = _entity_type_to_class[properties['entityType']]
        return cls(properties=properties, annotations=annotations)

    @classmethod
    def to_entity(cls, entity):
        """Coerse dictionary to Entity, but pass Entities through"""
        if isinstance(entity, Entity):
            return entity
        return Entity.create(properties=entity)


    def __new__(typ, *args, **kwargs):
        obj = object.__new__(typ, *args, **kwargs)
        ## make really sure that properties and annotations exist before
        ## any object methods get invoked
        obj.__dict__['properties'] = DictObject()
        obj.__dict__['annotations'] = DictObject()
        return obj


    def __init__(self, properties=None, annotations=None, **kwargs):

        if properties:
            if isinstance(properties, collections.Mapping):
                if 'annotations' in properties and isinstance(properties['annotations'], collections.Mapping):
                    annotations.update(properties['annotations'])
                    del properties['annotations']
                self.__dict__['properties'].update(properties)
            else:
                raise Exception('Unknown argument type: properties is a %s' % str(type(properties)))

        if annotations:
            if isinstance(annotations, collections.Mapping):
                self.__dict__['annotations'].update(annotations)
            elif isinstance(annotations, basestring):
                self.properties['annotations'] = annotations
            else:
                raise Exception('Unknown argument type: annotations is a %s' % str(type(annotations)))

        for key, value in kwargs.items():
            self.__setitem__(key, value)


    def __setattr__(self, key, value):
        return self.__setitem__(key, value)
        # if key in self.__dict__:
        #     ## if we assign like so:
        #     ##   entity.annotations = {'foo';123, 'bar':'bat'}
        #     ## wrap the dictionary in a DictObject so we can
        #     ## later do:
        #     ##   entity.annotations.foo = 'bar'
        #     if key=='annotations' and not isinstance(value, DictObject):
        #         value = DictObject(value)
        #     object.__setattr__(self, key, value)
        # else:
        #     self.__setitem__(key, value)


    def __setitem__(self, key, value):
        if key in self.__dict__:
            ## if we assign like so:
            ##   entity.annotations = {'foo';123, 'bar':'bat'}
            ## wrap the dictionary in a DictObject so we can
            ## later do:
            ##   entity.annotations.foo = 'bar'
            if key=='annotations' and not isinstance(value, DictObject):
                value = DictObject(value)
            self.__dict__[key] = value
        elif key in self.__class__._property_keys:
            self.properties[key] = value
        else:
            self.annotations[key] = value

    #TODO def __delattr__

    def __getattr__(self, key):
        ## note that __getattr__ is only called after an attempt to
        ## look the key up in the object's dictionary has failed.
        return self.__getitem__(key)


    def __getitem__(self, key):
        if key in self.__dict__:
            return self.__dict__[key]
        elif key in self.properties:
            return self.properties[key]
        elif key in self.annotations:
            return self.annotations[key]
        else:
            raise KeyError(key)

    def __delitem__(self, key):
        if key in self.properties:
            del self.properties[key]
        elif key in self.annotations:
            del self.annotations[key]


    def __iter__(self):
        return iter(self.keys())


    def __len__(self):
        return len(self.keys())


    def keys(self):
        """return a set of property and annotation keys"""
        return set(self.properties.keys() + self.annotations.keys())

    def has_key(self, key):
        """Is the given key a property or annotation?"""
        return key in self.properties or key in self.annotations

    def __str__(self):            
        from cStringIO import StringIO
        f = StringIO()

        f.write('%s: %s (%s)\n' % (self.__class__.__name__, self.properties.get('name', 'None'), self['id'] if 'id' in self else '-',))

        def write_kvps(dictionary, key_filter=None):
            for key in sorted(dictionary.keys()):
                if (not key_filter) or key_filter(key):
                    f.write('  ')
                    f.write(key)
                    f.write('=')
                    f.write(str(dictionary[key]))
                    f.write('\n')

        write_kvps(self.__dict__, lambda key: not (key in ['properties', 'annotations'] or key.startswith('__')))

        f.write('properties:\n')
        write_kvps(self.properties)

        f.write('annotations:\n')
        write_kvps(self.annotations)

        return f.getvalue()

    def __repr__(self):
        """Returns an eval-able representation of the entity"""
        from cStringIO import StringIO
        f = StringIO()
        f.write(self.__class__.__name__)
        f.write("(")
        f.write(", ".join(
            {"%s=%s" % (str(key), value.__repr__(),) for key, value in 
                itertools.chain(
                    filter(lambda (k,v): not (k in ['properties', 'annotations'] or k.startswith('__')), self.__dict__.items()),
                    self.properties.items(),
                    self.annotations.items())}))
        f.write(")")
        return f.getvalue()



class Project(Entity):
    _synapse_class = 'org.sagebionetworks.repo.model.Project'

    def __init__(self, name=None, properties=None, annotations=None, **kwargs):
        if name: kwargs['name'] = name
        super(Project, self).__init__(entityType=Project._synapse_class, properties=properties, annotations=annotations, **kwargs)


class Folder(Entity):
    _synapse_class = 'org.sagebionetworks.repo.model.Folder'

    def __init__(self, name=None, parent=None, properties=None, annotations=None, **kwargs):
        if name: kwargs['name'] = name
        if parent: kwargs['parentId'] = id_of(parent)
        super(Folder, self).__init__(entityType=Folder._synapse_class, properties=properties, annotations=annotations, **kwargs)


class File(Entity, Versionable):
    _property_keys = Entity._property_keys + Versionable._property_keys + ['dataFileHandleId']
    _synapse_class = 'org.sagebionetworks.repo.model.FileEntity'

    ## File(path="/path/to/file", synapseStore=True, parentId="syn101")
    def __init__(self, path=None, parent=None, synapseStore=True, properties=None, annotations=None, **kwargs):
        if path and 'name' not in kwargs:
            kwargs['name'] = os.path.basename(path)
        if parent: kwargs['parentId'] = id_of(parent)
        super(File, self).__init__(entityType=File._synapse_class, properties=properties, annotations=annotations, **kwargs)
        self.__dict__['path'] = path



## Deprecated, but kept around for compatibility with
## old-style Data, Code, Study, etc. entities
class Locationable(Versionable):
    _synapse_class = 'org.sagebionetworks.repo.model.Locationable'
    _property_keys = Versionable._property_keys + ['locations', 'md5', 'contentType', 's3Token']


class Analysis(Entity):
    _synapse_class = 'org.sagebionetworks.repo.model.Analysis'


class Code(Entity, Locationable):
    _synapse_class = 'org.sagebionetworks.repo.model.Code'
    _property_keys = Entity._property_keys + Locationable._property_keys


class Data(Entity, Locationable):
    _synapse_class = 'org.sagebionetworks.repo.model.Data'
    _property_keys = Entity._property_keys + Locationable._property_keys


class Study(Entity, Locationable):
    _synapse_class = 'org.sagebionetworks.repo.model.Study'
    _property_keys = Entity._property_keys + Locationable._property_keys


class Summary(Entity, Versionable):
    _synapse_class = 'org.sagebionetworks.repo.model.Summary'
    _property_keys = Entity._property_keys + Versionable._property_keys



## Create a mapping from Synapse class (as a string) to the equivalent
## Python class.
_entity_type_to_class = {}
for cls in itersubclasses(Entity):
    _entity_type_to_class[cls._synapse_class] = cls

