import os
import random
import pickle
from datetime import datetime
from enum import Enum
from os import listdir
from os.path import isfile, join
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import discord


class Channel(Enum):
    """ A Discord channel ID."""
    TEST_DES_BOTS = 0
    ANKI = 0


class Message:
    """ A representation of a Discord message, with a text and an optional filename."""

    def __init__(self, text: str, filename: str = None):
        self.text = text
        self.filename = filename

    def __repr__(self):
        return f"{self.text} {self.filename}"


class SubjectCard:
    """ A subject and a card (either a question or an answer). """

    def __init__(self, subject_name: str, card_name: str):
        self.subject_name = subject_name
        self.card_name = card_name


def number_to_emote(nb):
    """ Converts a single-digit number into the corresponding Discord emote. """

    if nb == 0: return ":zero:"
    if nb == 1: return ":one:"
    if nb == 2: return ":two:"
    if nb == 3: return ":three:"
    if nb == 4: return ":four:"
    if nb == 5: return ":five:"
    if nb == 6: return ":six:"
    if nb == 7: return ":seven:"
    if nb == 8: return ":eight:"
    if nb == 9: return ":nine:"
    raise ValueError("Argument must be an integer between 0 and 9.")


def timeprint(*message):
    """ Prints messages to the console with a timestamp. """

    dt_string = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    print(f"[{dt_string}]", *message)


def get_foldernames_from(folder: str):
    """ Retrieves all folder names from a specified folder path. """

    return [f.name for f in os.scandir(folder) if f.is_dir()]


def get_question_filenames_from(folder):
    """ Retrieves all question filenames from a specified folder path. """

    return [f for f in listdir(folder) if isfile(join(folder, f)) and f.endswith("q.png")]


class MyClient(discord.Client):
    """ A Discord bot regularly posting questions and answers. """

    # @@@@@@@@@@@@@@@@ #
    # @@@@@ INIT @@@@@ #
    # @@@@@@@@@@@@@@@@ #

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # =================================== #
        # ========== MAIN SETTINGS ========== #
        # =================================== #

        self.channel = Channel.TEST_DES_BOTS
        """ The channel ID the bot should post in. """

        self.daily_question_nb = 5
        """ The number of questions to be drawn each time. """

        self.react_emoji = "👌"
        """ The reaction emoji to be used for asking answers via private messages. """

        self.allow_answers_with_reactions = False
        """ Whether the bot allows answers via private messages or not. """

        # ==================================== #
        # ========== ADMINISTRATION ========== #
        # ==================================== #

        self.admins = ["Anon#0000"]
        """ The list of Discord usernames who have access to the bot commands. """

        self.token = 'token'  # PRIVATE
        """ The token of the bot. """

        # ================================= #
        # ========== ROOT FOLDER ========== #
        # ================================= #

        self.subjects_root = r"../DailyAnki/files"
        """ The main directory containing all the folders (one folder per subject). """

        # ============================= #
        # ========== BACKUPS ========== #
        # ============================= #

        self.all_questions_save = r"./all_questions.sav"
        """ A backup file containing all the questions to be drawn. """

        self.current_questions_save = r"./current_questions.sav"
        """ A backup file containing all the last drawn questions. """

        self.current_answers_save = r"./current_answers.sav"
        """ A backup file containing all the last drawn answers. """

        self.savedata = [  # (<path>, <attribute_name_of_data_to_be_saved>)
            (self.all_questions_save, 'all_questions'),
            (self.current_questions_save, 'subjects_questions_messages'),
            (self.current_answers_save, 'subjects_answers_messages')
        ]
        """ A data table gathering data to be saved/loaded. """

        # ====================================== #
        # ========== INNER ATTRIBUTES ========== #
        # ====================================== #

        self.all_questions = {}  # dic[<question>] = <answer>
        """ The dictionary with question paths as its keys, and answer paths as its values. """

        self.subjects_questions_messages = []
        """ The list of properly formatted Discord messages of the questions. """

        self.subjects_answers_messages = []
        """ The list of properly formatted Discord messages of the answers. """

        self.questions_ids_with_answers = {}  # dic[<discord message id>] = <prepared answer message>
        """ The dictionary used to send answers via private messages. """

    # @@@@@@@@@@@@@@@@@@@ #
    # @@@@@ BACKUPS @@@@@ #
    # @@@@@@@@@@@@@@@@@@@ #

    def load_data(self):
        """ Load data described in `savedata`. """

        for filename, fieldname in self.savedata:
            if isfile(filename):
                timeprint(f'Data loading from "{filename}" ...')
                f = open(filename, "rb")
                setattr(self, fieldname, pickle.load(f, encoding='utf-8'))
                timeprint(f'Data loaded from "{filename}" : {getattr(self, fieldname)}.')

    def save_data(self):
        """ Save data described in `savedata`. """

        for filename, fieldname in self.savedata:
            timeprint(f'Data saving to "{filename}".')
            f = open(filename, "wb+")
            pickle.dump(getattr(self, fieldname), f)
            timeprint(f'Data saved to "{filename}".')

    # @@@@@@@@@@@@@@@@@@@ #
    # @@@@@ UTILITY @@@@@ #
    # @@@@@@@@@@@@@@@@@@@ #

    def get_all_question_paths(self):
        """ Returns a dictionary with question paths as its keys, and answer paths as its values. """

        all_questions_dic = {}
        for subject in get_foldernames_from(self.subjects_root):
            subject_folder = f"{self.subjects_root}\\{subject}"
            for question in get_question_filenames_from(subject_folder):
                question_card = SubjectCard(subject, question)
                answer = question.replace("q", "a")  # Kinda hacky, but works
                answer_card = SubjectCard(subject, answer)

                all_questions_dic[question_card] = answer_card
        return all_questions_dic

    def draw_questions(self):
        """ Draw a total of `daily_question_nb` questions within the available ones (in `all_questions`), and
        prepare the associated Discord messages. The deck is refilled when all questions have already been drawn. """

        self.subjects_questions_messages = []
        self.subjects_answers_messages = []
        # questions_ids_with_answers is not reset, such that users can be sent answers from older questions.
        # all_questions is not reset, in order to draw all cards before seing the same card twice.

        for i in range(self.daily_question_nb):
            # If there are no more questions, refill
            if len(self.all_questions) == 0:
                self.all_questions = self.get_all_question_paths()
                timeprint(f"Refilled question list : {len(self.all_questions)}")

            # Choose a random question-answer and delete it from the pickable question pool
            question_card = random.choice(list(self.all_questions.keys()))
            answer_card = self.all_questions[question_card]
            del self.all_questions[question_card]

            # Prepare messages
            self.subjects_questions_messages.append(
                self.prepare_message(question_card, i + 1)
            )
            self.subjects_answers_messages.append(
                self.prepare_message(answer_card, i + 1)
            )

        timeprint(f"Drawn questions : {self.subjects_questions_messages}")
        timeprint(f"Questions left to be drawn : {len(self.all_questions)}")

        self.save_data()

    def prepare_message(self, card, i):
        """ Prepares a Discord formatted message from a `SubjectCard` and a message number. """

        return Message(
            f'_ _\n'
            f'{number_to_emote(i)} **Matière** : "*{card.subject_name}*", **fiche** : "*{card.card_name}*"',
            filename=self.subjects_root + "\\" + card.subject_name + "\\" + card.card_name
        )

    def compile_discord_file(self, filename):
        """ Creates a Discord file from the desired `filename`. Mandatory since all Discord attachments can only be
        used once. """

        return discord.File(filename)

    async def send_image_message(self, recipient, message: Message):
        """ Sends a `Message` to the desired `recipient` (can be a channel, a user, ...). """

        return await recipient.send(message.text, file=self.compile_discord_file(message.filename))

    async def post_questions(self):
        """ Posts questions in the Discord channel which ID is held in `self.channel`. """

        timeprint("Posting questions.")

        await self.channel.send(
            f":blush: **Bonjour à toutes et à tous** :blush:"
            f"\n\nNous sommes le {datetime.now().strftime('%d/%m/%Y')}, et voici {self.daily_question_nb} "
            f"nouvelles questions pour vous :"
        )

        for (question, answer) in zip(self.subjects_questions_messages, self.subjects_answers_messages):
            discord_message = await self.send_image_message(self.channel, question)
            self.questions_ids_with_answers[discord_message.id] = answer

            if self.allow_answers_with_reactions:
                await discord_message.add_reaction(self.react_emoji)

        await self.channel.send(
            f"_ _\n:brain: A vous de jouer ! :brain:"
            f"\n================="
            f"\n_ _"
        )

    async def send_answers(self):
        """ Posts answers in the Discord channel which ID is held in `self.channel`. """

        timeprint("Posting answers.")

        await self.channel.send(
            ":slight_smile: **Merci d'avoir fait l'effort de participer !** :slight_smile:"
            "\n\nVoici les réponses aux questions d'aujourd'hui :"
        )

        for answer in self.subjects_answers_messages:
            await self.send_image_message(self.channel, answer)

        await self.channel.send(
            f"_ _\n:trophy: On lâche rien ! A demain ! :trophy:"
            "\n================="
            "\n================="
            "\n_ _"
            "\n_ _"
        )

    # @@@@@@@@@@@@@@@@@@@@@@@@@ #
    # @@@@@ BOT OVERRIDES @@@@@ #
    # @@@@@@@@@@@@@@@@@@@@@@@@@ #

    async def on_ready(self):
        # Set channel
        self.channel = self.get_channel(self.channel.value)

        # Load existing saved data
        self.load_data()

        timeprint('Logged in as', self.user.name, self.user.id)
        print('------------------')

        # Schedule tasks
        scheduler = AsyncIOScheduler()
        scheduler.add_job(self.draw_questions, CronTrigger(hour="8", minute="59", second="0"))
        scheduler.add_job(self.post_questions, CronTrigger(hour="9", minute="0", second="0"))
        scheduler.add_job(self.send_answers, CronTrigger(hour="22", minute="0", second="0"))
        scheduler.start()

    async def on_message(self, message):
        # The bot shouldn't reply to itself
        if message.author.id == self.user.id:
            return

        # Only admins can use commands
        if str(message.author) not in self.admins:
            return

        # Activates/deactivates reaction private messages
        if message.content.startswith('!reaction'):
            self.allow_answers_with_reactions = not self.allow_answers_with_reactions
            timeprint(f"[{message.author}] : Setting reactions to {self.allow_answers_with_reactions}.")

        # Manually draw new questions
        if message.content.startswith('!draw'):
            timeprint(f"[{message.author}] : Manually drawing new questions.")
            self.draw_questions()

        # Manually post questions
        if message.content.startswith('!questions'):
            timeprint(f"[{message.author}] : Manually posting questions.")
            await self.post_questions()

        # Manually post answers
        if message.content.startswith('!answers'):
            timeprint(f"[{message.author}] : Manually posting answers.")
            await self.send_answers()

    async def on_reaction_add(self, reaction, user):
        # Only allow reaction answers if the setting allows it
        if not self.allow_answers_with_reactions:
            return

        # The bot shouldn't reply to itself
        if user == client.user:
            return

        # Handle answers via private messages, through emoji reactions
        if str(reaction.emoji) == self.react_emoji:
            answer = self.questions_ids_with_answers[reaction.message.id]
            timeprint(f'Private answer : "{user}" asked for "{answer}".')
            await self.send_image_message(user, answer)
            timeprint(f'Private answer : "{user}" received "{answer}".')


client = MyClient()
client.run(client.token)
