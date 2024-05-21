import logging
from textwrap import dedent

from django.core.management.base import BaseCommand, CommandError

from rdmo.domain.models import Attribute
from rdmo.management.utils import replace_uri_in_template_string
from rdmo.projects.models import Value
from rdmo.views.models import View

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Replace an attribute with another attribute across multiple models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            required=True,
            help='The URI of the source attribute that will be replaced by the target and will be deleted'
        )
        parser.add_argument(
            '--target',
            required=True,
            help='The URI of the target attribute that will be used to replace the source'
        )
        parser.add_argument(
            '--save',
            action='store_true',
            help='''If specified, the changes will be saved and the source attribute will be deleted.\
                    If not specified, the command will do a dry run.'''
        )

    def handle(self, *args, **options):
        source = options['source']
        target = options['target']
        save = options['save']
        verbosity = options.get('verbosity', 1)

        source = get_valid_attribute(source, message_name='Source')
        target = get_valid_attribute(target, message_name='Target')

        if source == target:
            raise CommandError("Source and Target attribute are the same, nothing to do.")

        results = {}
        related_model_fields = [i for i in Attribute._meta.get_fields() \
                          if i.is_relation and not i.many_to_many and i.related_model is not Attribute]
        for related_field in related_model_fields:
            replaced_model_result = replace_attribute_on_related_model_instances(
                related_field,
                source=source,
                target=target,
                save=save
            )
            results[related_field.related_model._meta.verbose_name_raw] = replaced_model_result

        view_template_result = replace_attribute_in_view_template(source=source, target=target, save=save)
        results[View._meta.verbose_name_raw] = view_template_result

        if save and all(a['saved'] for i in results.values() for a in i):
            try:
                source.delete()
            except source.DoesNotExist:
                pass

        if verbosity >= 1:
            if verbosity >= 2:
                affected_instances_msg = make_affected_instances_message(results)
                if affected_instances_msg:
                    self.stdout.write(affected_instances_msg)
            affect_elements_msg = make_elements_message(results)
            affected_projects_msg = make_affected_projects_message(results)
            if save:
                self.stdout.write(self.style.SUCCESS(
                    f"Successfully replaced source attribute {source.uri} with {target.uri}.\n"
                    f"Source attribute {source.uri} was deleted.\n"
                    f"{affect_elements_msg}\n"
                    f"{affected_projects_msg}"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Source attribute {source.uri} can be replaced with {target.uri}.\n"
                    f"{affect_elements_msg}\n"
                    f"{affected_projects_msg}"
                ))


def get_valid_attribute(attribute, message_name=''):
    if isinstance(attribute, str):
        attribute_uri = attribute
        try:
            attribute = Attribute.objects.get(uri=attribute_uri)
        except Attribute.DoesNotExist as e:
            raise CommandError(f"{message_name} attribute {attribute_uri} does not exist.") from e
        except Attribute.MultipleObjectsReturned as e:
            raise CommandError(f"{message_name} attribute {attribute_uri} returns multiple objects.") from e
    elif not isinstance(attribute, Attribute):
        raise CommandError(f"{message_name} argument should be of type Attribute.")

    if attribute.get_descendants():
        raise CommandError(f"{message_name} attribute '{attribute}' with descendants is not supported.")

    return attribute

def replace_attribute_on_related_model_instances(related_field,
                                           source=None,
                                           target=None,
                                           save=False
                                           ):
    model = related_field.related_model
    lookup_field = related_field.remote_field.name
    qs = model.objects.filter(**{lookup_field: source})

    replacement_results = []
    for instance in qs:
        instance_source = getattr(instance, lookup_field)

        if isinstance(instance_source, Attribute) and instance_source != source:
            raise CommandError("Instance attribute should be equal to the source attribute")

        setattr(instance, lookup_field, target)

        if save:
            instance.save()
        replacement_results.append({
            'model_name': model._meta.verbose_name_raw,
            'instance': instance,
            'source': source,
            'target': target,
            'saved': save,
        })
    return replacement_results


def replace_attribute_in_view_template(source=None, target=None, save=False ):
    qs = View.objects.filter(**{"template__contains": source.path})
    replacement_results = []
    for instance in qs:

        template_target = replace_uri_in_template_string(instance.template, source, target)
        instance.template = template_target

        if save:
            instance.save()
        replacement_results.append({
            'model_name': View._meta.verbose_name_raw,
            'instance': instance,
            'source': source,
            'target': target,
            'saved': save,
        })
    return replacement_results


def make_elements_message(results):
    element_counts = ", ".join([f"{k.capitalize()}({len(v)})" for k, v in results.items() if v])
    if not element_counts or not any(results.values()):
        return "No elements affected."
    return f"Affected elements: {element_counts}"


def make_affected_projects_message(results):
    value_results = results.get(Value._meta.verbose_name_raw, [])
    if not value_results:
        return "No projects affected."
    msg = "Affected Projects:"
    for project in {i['instance'].project for i in value_results}:
        msg += f"\n\tproject={project} (id={project.id})"
    return msg


def make_affected_instances_message(results):
    if not results:
        return ""
    msg = ""
    for k, merger_results in results.items():
        if not merger_results:
            continue
        msg += f"Merger results for model {k.capitalize()} ({len(merger_results)})"
        msg += '\n'
        for result in merger_results:
            msg += dedent(f'''\
                Model={result['model_name']}
                instance={result['instance']}
                source={result['source'].uri}
                target={result['target'].uri}
                saved={result['saved']}
            ''')
            if hasattr(result['instance'], 'project'):
                msg += f"\nproject={result['instance'].project}"
        msg += '\n'
    return msg
