from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Commentary",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("label", models.CharField(max_length=200)),
                ("author", models.CharField(blank=True, max_length=200)),
                ("source_repo", models.CharField(blank=True, max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name="CommentaryEntry",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("target_urn", models.CharField(db_index=True, max_length=300)),
                ("target_key", models.CharField(db_index=True, max_length=120)),
                ("ref_start", models.CharField(db_index=True, max_length=64)),
                ("ref_end", models.CharField(db_index=True, max_length=64)),
                ("citation_urn", models.CharField(blank=True, max_length=300)),
                ("lemma", models.CharField(blank=True, max_length=200)),
                ("content_html", models.TextField()),
                ("commentary", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="entries",
                    to="localcomm.commentary",
                )),
            ],
            options={
                "ordering": ["target_key", "ref_start", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="commentaryentry",
            index=models.Index(
                fields=["target_key", "ref_start", "ref_end"],
                name="localcomm_entry_target_idx",
            ),
        ),
    ]
