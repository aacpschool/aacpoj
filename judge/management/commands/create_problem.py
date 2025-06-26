from django.core.management.base import BaseCommand
from judge.models import Problem, ProblemGroup, ProblemType, Language, ProblemTranslation
from django.contrib.auth.models import User
import os
import yaml
import datetime

class Command(BaseCommand):
    help = 'create an empty problem'

    def add_arguments(self, parser):
        parser.add_argument('code')
        parser.add_argument('name')
        parser.add_argument('body_path')          # 改成讀檔路徑
        parser.add_argument('--type', default='batch',
                            help='ProblemType name (default: batch)')
        parser.add_argument('--group', default='Uncategorized',
                            help='ProblemGroup name (default: Uncategorized)')
        parser.add_argument('--time', type=float, default=1.0)
        parser.add_argument('--memory', type=int, default=262144)  # KiB
        parser.add_argument('--points', type=int, default=100)
        parser.add_argument('--update', action='store_true',
                            help='If the problem already exists, update it instead of failing')

    def handle(self, *args, **opt):
        pg, _ = ProblemGroup.objects.get_or_create(name=opt['group'])
        # Ensure a ProblemType (problem category) with this name exists; create if missing
        ptype, _ = ProblemType.objects.get_or_create(name=opt['type'])

        # --- Load extra settings from init.yml (translations, allowed_languages) ---
        problem_dir = os.path.dirname(opt['body_path'])
        init_path = os.path.join(problem_dir, 'init.yml')
        cfg = {}
        if os.path.exists(init_path):
            with open(init_path, 'r') as f:
                cfg = yaml.safe_load(f) or {}

        # --- optional publish datetime ---
        publish_dt = None
        if 'publish' in cfg:
            # single string e.g. "2025-06-25 21:12:52"
            publish_dt = datetime.datetime.fromisoformat(str(cfg['publish']).strip())
        elif 'publish_date' in cfg or 'publish_time' in cfg:
            date_part = cfg.get('publish_date', '')
            time_part = cfg.get('publish_time', '00:00:00')
            if date_part:
                publish_dt = datetime.datetime.fromisoformat(f"{date_part.strip()} {time_part.strip()}")

        # Create or update the Problem record
        try:
            problem = Problem.objects.get(code=opt['code'])
            if not opt['update']:
                self.stderr.write(self.style.ERROR(
                    f"Problem '{opt['code']}' already exists — use --update to overwrite."))
                return
            # --- overwrite existing fields ---
            problem.name = opt['name']
            problem.description = open(opt['body_path']).read()
            problem.time_limit = opt['time']
            problem.memory_limit = opt['memory']
            problem.points = opt['points']
            problem.group = pg
            if publish_dt is not None:
                problem.date = publish_dt
            problem.save()
            created = False
        except Problem.DoesNotExist:
            problem_kwargs = dict(
                code=opt['code'],
                name=opt['name'],
                description=open(opt['body_path']).read(),
                time_limit=opt['time'],
                memory_limit=opt['memory'],
                points=opt['points'],
                group=pg,
            )
            if publish_dt is not None:
                problem_kwargs['date'] = publish_dt
            problem = Problem(**problem_kwargs)
            problem.save()
            created = True
        problem.types.set([ptype])   # 正確設定 Many-to-Many

        # --- allowed_languages from init.yml ---
        if cfg.get('allowed_languages'):
            lang_objects = []
            for code in cfg['allowed_languages']:
                lang_obj, _ = Language.objects.get_or_create(
                    key=code,
                    defaults={'name': code, 'common_name': code}
                )
                lang_objects.append(lang_obj)
            problem.allowed_languages.set(lang_objects)

        # --- translations from init.yml ---
        for tr in cfg.get('translations', []):
            lang_obj, _ = Language.objects.get_or_create(
                key=tr['lang'],
                defaults={'name': tr['lang'], 'common_name': tr['lang']}
            )
            tr_body_path = os.path.join(problem_dir, tr['body'])
            tr_body = open(tr_body_path).read() if os.path.exists(tr_body_path) else ''
            # first create/update with the fields we are certain exist
            translation, _ = ProblemTranslation.objects.update_or_create(
                problem=problem,
                language=lang_obj,
                defaults={
                    # some DMOJ forks use 'name', others 'title'
                    'name': tr.get('name', problem.name) if hasattr(ProblemTranslation, 'name') else tr.get('name', problem.name),
                }
            )
            # figure out which field holds the statement text
            for field in ('body', 'text', 'description', 'statement'):
                if hasattr(translation, field):
                    setattr(translation, field, tr_body)
                    translation.save(update_fields=[field])
                    break

        # --- authors from init.yml ---
        if cfg.get('authors'):
            user_objs = []
            for username in cfg['authors']:
                try:
                    user_objs.append(User.objects.get(username=username))
                except User.DoesNotExist:
                    self.stderr.write(
                        self.style.WARNING(f"User '{username}' 不存在，略過作者設定"))
            if user_objs:
                problem.authors.set([u.pk for u in user_objs])