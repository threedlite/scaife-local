from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Dictionary",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("label", models.CharField(max_length=200)),
                ("lang", models.CharField(max_length=8)),
            ],
        ),
        migrations.CreateModel(
            name="DictionaryEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("headword", models.CharField(max_length=200)),
                ("headword_normalized", models.CharField(db_index=True, max_length=200)),
                ("headword_normalized_stripped", models.CharField(db_index=True, max_length=200)),
                ("intro_text", models.TextField()),
                ("sort_order", models.PositiveIntegerField(db_index=True, default=0)),
                ("dictionary", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="entries",
                    to="localdict.dictionary",
                )),
            ],
            options={
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="dictionaryentry",
            index=models.Index(
                fields=["dictionary", "headword_normalized_stripped"],
                name="localdict_d_diction_ed4c5f_idx",
            ),
        ),
    ]
