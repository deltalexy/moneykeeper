import json
import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor
import pickle
import os
from datetime import datetime

class Vals():

    def load(self):
        newdict = {'budget': 0,
                     'hold': 0,
                     'itohold': 0,
                     'holdniv': 0,
                     'buffer': 0,
                     'zicht': 0,
                     'mastercard': 0,
                     'bpaid': 0,
                     'cash': 0,
                     'inhouse': 0,
                     'cheques': 0,
                     'achterkomend': 0,
                     'achterinfo': '',
                     'controledatum': '',
                     'log': ''}
        if os.path.exists('moneykeeper.pickle'):
            with open('moneykeeper.pickle', 'rb') as file:
                valdict = pickle.load(file)
            listy = list(valdict.keys())
            for key in listy:
                if isinstance(valdict[key], float):
                    valdict[key] = round(valdict[key], 2)
                if key not in newdict.keys():
                    valdict.pop(key, None)
            for key in newdict.keys():
                if key not in valdict.keys():
                    valdict[key] = newdict[key]
            return valdict
        else:
            return newdict

    def save(self):
        with open('moneykeeper.pickle', 'wb') as file:
            pickle.dump(self.__dict__, file)

    def __init__(self):
        valdict = self.load()
        for key in valdict.keys():
            setattr(self, key, valdict[key])

class Main(QWidget):

    def settingsclick(self):
        self.save()
        self.settingspage = Settings(self)
        self.settingspage.show()

    def translogclick(self):
        #
        self.translog = Logviewer(self.values)
        self.translog.show()

    def reportclick(self):
        #
        self.report = Report(self.values.log, [['Volledig rapport']])
        self.report.show()

    def searchclick(self):
        #
        self.search = Searcher(self.values)
        self.search.show()

    def controleclick(self):
        self.save()
        self.controlepage = Controle(self)
        self.controlepage.show()

    def reload(self):

        self.budget_label.setText(str(round(self.values.budget + self.temp['budget'], 2)))
        self.hold_label.setText(str(round(self.values.hold + self.temp['hold'], 2)))
        self.addbox.setText(self.temp['log'])

    def save(self):
        self.values.budget += round(self.temp['budget'], 2)
        self.values.hold += round(self.temp['hold'], 2)
        if self.values.log == "":
            idcounter = 0
        else:
            idcounter = int(self.values.log.split('\n')[-2].split('\t')[0])+1
        for element in self.temp['log'].split('\n'):
            if element != '':
                self.values.log += '\t'.join([str(idcounter), element+'\n'])
                idcounter += 1
        self.temp = {'budget':0, 'hold':0, 'log':''}
        self.values.save()
        self.reload()

    def reset(self):
        self.temp['budget'] = 0
        self.temp['hold'] = 0
        self.temp['log'] = ''
        self.reload()

    def transaction(self, kind):
        if self.info_line.text() != '':
            if self.datum_line.text() == '':
                datum = datetime.today().strftime('%d/%m/%y')
            else:
                try:
                    date_time_obj = datetime.strptime(self.datum_line.text(), '%d/%m/%Y')
                except:
                    date_time_obj = datetime.strptime(self.datum_line.text(), '%d/%m/%y')
                datum = date_time_obj.strftime('%d/%m/%y')
            info = self.info_line.text()
            value = -round(eval(self.bedrag_line.text()), 2)
            if kind == 'I' or kind == 'S':
                value *= -1
            text = '\t'.join([datum, kind, str(value), info])
            self.temp['log'] += (text + '\n')
            self.temp['budget'] += value
        else:
             self.msg = Dialog('Geen info!', 'warning')
             self.msg.show()
             return False
        self.bedrag_line.setText('')
        self.datum_line.setText('')
        self.info_line.setText('')
        self.reload()
        return True

    def ibutclick(self):
        val = self.bedrag_line.text()
        if self.transaction('I'):
            if (self.values.hold + self.temp['hold']) >= self.values.holdniv:
                self.bedrag_line.setText(str(float(val)*self.values.itohold/100))
            elif (self.values.hold + self.temp['hold'] + float(val)) <= self.values.holdniv:
                self.bedrag_line.setText(val)
            else:
                opvulling = self.values.holdniv - self.values.hold - self.temp['hold']
                overschot = float(val) - opvulling
                budgethold = opvulling + overschot*self.values.itohold/100
                self.bedrag_line.setText(str(budgethold))
            self.budget_hold()

    def lbutclick(self):
        self.transaction('L')

    def nbutcklick(self):
        bedrag = float(self.bedrag_line.text())
        self.transaction('N')
        self.bedrag_line.setText(str(-bedrag))
        self.budget_hold()

    def bbutclick(self):
        bedrag = float(self.bedrag_line.text())
        self.transaction('B')
        self.bedrag_line.setText(str(-bedrag))
        self.budget_hold()

    def ubutcklick(self):
        self.transaction('U')

    def rbutclick(self):
        self.transaction('R')

    def abutclick(self):
        self.transaction('A')

    def cbutclick(self):
        self.transaction('C')

    def sparen(self):
        val = float(self.bedrag_line.text())
        if self.transaction('S'):
            self.bedrag_line.setText(str(-val))
            self.budget_hold()
            self.temp['budget'] -= 2*val
            self.reload()

    def budget_hold(self):
        val = round(float(self.bedrag_line.text()),2)
        self.temp['budget'] -= val
        self.temp['hold'] += val
        self.bedrag_line.setText('')
        self.reload()

    def __init__(self):
        QWidget.__init__(self)
        self.setWindowTitle('Moneykeeper')
        self.values = Vals()
        self.temp = {'budget':0, 'hold':0, 'log':''}

        self.bedrag_line = QLineEdit()
        self.datum_line = QLineEdit()
        self.info_line = QLineEdit()
        self.budget_label = QLabel(str(self.values.budget))
        self.hold_label = QLabel(str(self.values.hold))
        self.ibut = QPushButton('I')
        self.lbut = QPushButton('L')
        self.nbut = QPushButton('N')
        self.bbut = QPushButton('B')
        self.ubut = QPushButton('U')
        self.rbut = QPushButton('R')
        self.abut = QPushButton('A')
        self.cbut = QPushButton('C')
        self.budget_hold_but = QPushButton('budget -> hold')
        self.spaarbut = QPushButton('sparen')
        self.savebut = QPushButton('save')
        self.resetbut = QPushButton('reset')
        self.controle = QPushButton('controle')
        self.instellingen = QPushButton('instellingen')
        self.addbox = QTextEdit()
        self.seelogbut = QPushButton('volledig transactielog')
        self.reportbut = QPushButton('report')
        self.searchbut = QPushButton('search')

        self.ibut.clicked.connect(self.ibutclick)
        self.lbut.clicked.connect(self.lbutclick)
        self.nbut.clicked.connect(self.nbutcklick)
        self.bbut.clicked.connect(self.bbutclick)
        self.ubut.clicked.connect(self.ubutcklick)
        self.rbut.clicked.connect(self.rbutclick)
        self.abut.clicked.connect(self.abutclick)
        self.cbut.clicked.connect(self.cbutclick)
        self.budget_hold_but.clicked.connect(self.budget_hold)
        self.spaarbut.clicked.connect(self.sparen)
        self.savebut.clicked.connect(self.save)
        self.resetbut.clicked.connect(self.reset)
        self.controle.clicked.connect(self.controleclick)
        self.instellingen.clicked.connect(self.settingsclick)
        self.seelogbut.clicked.connect(self.translogclick)
        self.reportbut.clicked.connect(self.reportclick)
        self.searchbut.clicked.connect(self.searchclick)

        self.layout = QGridLayout()
        self.layout.addWidget(QLabel('bedrag'),1,0)
        self.layout.addWidget(self.bedrag_line, 1,1,1,3)
        self.layout.addWidget(QLabel('datum'),2,0)
        self.layout.addWidget(self.datum_line,2,1,1,3)
        self.layout.addWidget(QLabel('info'),3,0)
        self.layout.addWidget(self.info_line,3,1,1,3)
        self.layout.addWidget(QLabel('budget'),0,0)
        self.layout.addWidget(QLabel('hold'),0,2)
        self.layout.addWidget(self.budget_label,0,1)
        self.layout.addWidget(self.hold_label,0,3)
        self.layout.addWidget(self.ibut,4,0)
        self.layout.addWidget(self.lbut,4,1)
        self.layout.addWidget(self.bbut,5,0)
        self.layout.addWidget(self.nbut,5,1)
        self.layout.addWidget(self.ubut,4,2)
        self.layout.addWidget(self.rbut,4,3)
        self.layout.addWidget(self.abut,5,2)
        self.layout.addWidget(self.cbut,5,3)
        self.layout.addWidget(self.budget_hold_but, 6,0,1,2)
        self.layout.addWidget(self.spaarbut, 6,2,1,2)
        self.layout.addWidget(self.savebut, 7,0,1,2)
        self.layout.addWidget(self.resetbut, 7,2,1,2)
        self.layout.addWidget(self.controle, 8,0,1,2)
        self.layout.addWidget(self.instellingen, 8,2,1,2)
        self.layout.addWidget(self.addbox, 0,4,7,8)
        self.layout.addWidget(self.seelogbut, 7,4,1,8)
        self.layout.addWidget(self.reportbut, 8,4,1,4)
        self.layout.addWidget(self.searchbut, 8,8,1,4)
        self.setLayout(self.layout)

class Settings(QWidget):
    def changebutclick(self):
        self.values.budget = round(float(self.budget.text()),2)
        self.values.hold =  round(float(self.hold.text()),2)
        self.values.itohold =  round(float(self.itohold.text()),2)
        self.values.holdniv =  round(float(self.holdniv.text()),2)
        self.values.buffer =  round(float(self.buffer.text()),2)
        self.values.save()
        self.mainpage.reload()
        self.msg = Dialog('Waarden set.', 'info')
        self.msg.show()

    def __init__(self, mainpage):
        QWidget.__init__(self)
        self.setWindowTitle('Settings')
        self.mainpage = mainpage
        self.values = mainpage.values
        self.layout = QGridLayout()
        self.budget = QLineEdit(str(self.values.budget))
        self.hold = QLineEdit(str(self.values.hold))
        self.itohold = QLineEdit(str(self.values.itohold))
        self.holdniv = QLineEdit(str(self.values.holdniv))
        self.buffer = QLineEdit(str(self.values.buffer))
        self.changebut = QPushButton('set waarden')
        self.layout.addWidget(QLabel('budget'), 0,0)
        self.layout.addWidget(self.budget, 0,1)
        self.layout.addWidget(QLabel('hold'), 1,0)
        self.layout.addWidget(self.hold, 1,1)
        self.layout.addWidget(QLabel('% of I to hold'), 2,0)
        self.layout.addWidget(self.itohold, 2,1)
        self.layout.addWidget(QLabel('hold niveau'), 3,0)
        self.layout.addWidget(self.holdniv, 3,1)
        self.layout.addWidget(QLabel('buffer'), 4,0)
        self.layout.addWidget(self.buffer, 4,1)
        self.layout.addWidget(self.changebut, 5,0,1,2)

        self.changebut.clicked.connect(self.changebutclick)

        self.setLayout(self.layout)

class Controle(QWidget):

    def textchange(self):
        try:
            self.hebik.setText(str(self.hebiksum()))
            self.correctie.setText(str(self.correctiecalc()))
        except:
            pass

    def opslaan(self):
        self.values.zicht = float(self.zicht.text())
        self.values.mastercard = float(self.mastercard.text())
        self.values.bpaid = float(self.bpaid.text())
        self.values.cash = float(self.cash.text())
        self.values.inhouse = float(self.inhouse.text())
        self.values.cheques = float(self.cheques.text())
        self.values.achterkomend = float(self.achter.text())
        self.values.achterinfo = self.achterinfo.toPlainText()
        self.values.save()

    def bijwerken(self):
        self.opslaan()
        self.values.budget += self.correctiecalc()
        self.values.controledatum = datetime.today().strftime('%d/%m/%y')
        self.mainpage.reload()
        self.money.setText(str(self.moneysum()))
        self.datum.setText(self.values.controledatum)
        self.correctie.setText(str(self.correctiecalc()))
        self.values.save()

    def hebiksum(self):
        return round(float(self.zicht.text()) + float(self.mastercard.text()) + float(self.bpaid.text()) + float(self.cash.text()) + float(self.inhouse.text()) + float(self.cheques.text()) + float(self.achter.text()) - self.values.buffer, 2)

    def moneysum(self):
        return round(self.values.budget + self.values.hold, 2)

    def correctiecalc(self):
        return round(self.hebiksum() - self.moneysum(), 2)

    def __init__(self, mainpage):
        QWidget.__init__(self)
        self.setWindowTitle('Controle')
        self.mainpage = mainpage
        self.values = mainpage.values

        self.zicht = QLineEdit(str(self.values.zicht))
        self.mastercard = QLineEdit(str(self.values.mastercard))
        self.bpaid = QLineEdit(str(self.values.bpaid))
        self.cash = QLineEdit(str(self.values.cash))
        self.inhouse = QLineEdit(str(self.values.inhouse))
        self.cheques = QLineEdit(str(self.values.cheques))
        self.achter = QLineEdit(str(self.values.achterkomend))
        self.achterinfo = QTextEdit()
        self.achterinfo.setText(self.values.achterinfo)
        self.budget = QLabel(str(self.values.budget))
        self.hold = QLabel(str(self.values.hold))
        self.hebik = QLabel(str(self.hebiksum()))
        self.money = QLabel(str(self.moneysum()))
        self.correctie = QLabel(str(self.correctiecalc()))
        self.datum = QLabel(self.values.controledatum)
        self.savebut = QPushButton("Opslaan")
        self.bijwerkbut = QPushButton("Opslaan en Bijwerken")

        self.zicht.textChanged.connect(self.textchange)
        self.mastercard.textChanged.connect(self.textchange)
        self.bpaid.textChanged.connect(self.textchange)
        self.cash.textChanged.connect(self.textchange)
        self.inhouse.textChanged.connect(self.textchange)
        self.cheques.textChanged.connect(self.textchange)
        self.achter.textChanged.connect(self.textchange)
        self.savebut.clicked.connect(self.opslaan)
        self.bijwerkbut.clicked.connect(self.bijwerken)


        self.layout = QGridLayout()
        self.layout.addWidget(QLabel('Zichtrekening'), 0,0)
        self.layout.addWidget(QLabel('Mastercard'), 1,0)
        self.layout.addWidget(QLabel('Nickel'), 2,0)
        self.layout.addWidget(QLabel('Cash'), 3,0)
        self.layout.addWidget(QLabel('inhouse'), 4,0)
        self.layout.addWidget(QLabel('cheques'), 5,0)
        self.layout.addWidget(self.zicht, 0,1)
        self.layout.addWidget(self.mastercard, 1,1)
        self.layout.addWidget(self.bpaid, 2,1)
        self.layout.addWidget(self.cash, 3,1)
        self.layout.addWidget(self.inhouse, 4,1)
        self.layout.addWidget(self.cheques, 5,1)
        self.layout.addWidget(QLabel('Achterkomend'), 0,2)
        self.layout.addWidget(self.achter, 0,3)
        self.layout.addWidget(self.achterinfo, 1,2,5,2)
        self.layout.addWidget(QLabel('Wat ik heb'), 0,4)
        self.layout.addWidget(QLabel('Moneykeeper'), 1,4)
        self.layout.addWidget(QLabel('Correctie'), 2,4)
        self.layout.addWidget(self.hebik, 0,5)
        self.layout.addWidget(self.money, 1,5)
        self.layout.addWidget(self.correctie, 2,5)
        self.layout.addWidget(QLabel('Datum laatste bijwerking'), 4,4,1,2)
        self.layout.addWidget(self.datum, 5,4,1,2)
        self.layout.addWidget(self.savebut, 6,0,1,3)
        self.layout.addWidget(self.bijwerkbut, 6,3,1,3)
        self.setLayout(self.layout)

class Logviewer(QWidget):
    def changelog(self):
        self.values.log = self.logbox.toPlainText()
        self.values.save()
        self.msg = Dialog('Log bewerkt', 'info')
        self.msg.show()

    def __init__(self, values):
        QWidget.__init__(self)
        self.setWindowTitle('Logviewer')
        self.values = values
        self.logbox = QTextEdit()
        self.logbox.setText(self.values.log)
        self.logbox.moveCursor(QTextCursor.End)
        self.editbut = QPushButton('Bewerk log')
        self.editbut.clicked.connect(self.changelog)
        self.layout = QGridLayout()
        self.layout.addWidget(self.logbox, 0,0,8,8)
        self.layout.addWidget(self.editbut, 8,0,1,8)
        self.setLayout(self.layout)
        self.setFixedWidth(1200)
        self.setFixedHeight(800)

class Dialog(QMessageBox):
    def __init__(self, text, type):
        QMessageBox.__init__(self)
        self.setWindowTitle("Moneykeeper")
        if type == 'info':
            self.setIcon(QMessageBox.Icon.Information)
        if type == 'warning':
            self.setIcon(QMessageBox.Icon.Warning)
        self.setText(text)

class Report(QWidget):
    def dictioncreate(self):
        lijst = []
        prelijst = self.log.split("\n")
        for item in prelijst:
            if item != '':
                lijst.append(item.split("\t"))

        dictionary = {0: {}}  # creer diction met een key voor alles te samen, om som te nemen (de 0 key)
        for element in lijst:  # voor ieder element in de loglijst
            date = datetime.strptime(element[1], '%d/%m/%y')
            year = int(date.strftime('%Y'))  # bepaal datum van entry
            month = int(date.strftime('%m'))  # maand van entry
            day = int(date.strftime('%d'))  # dag van entry
            soort = element[2]  # soort van entry
            uitgave = float(element[3])  # bedrag van entry
            if dictionary.get(year):  # als het jaartal in dictionary zit
                dictionary[year][month][day].append(element)  # voeg element toe aan daglijst
            else:
                dictionary[year] = {0: {}}  # anders maak nieuwe key aan in dictionary voor jaar, met daarin een diction met een key voor alles te samen, om som te nemen (de 0 key)
                for i in range(12):
                    dictionary[year][i+1] = {}  # maak een dictionary aan voor de 12 maanden van het jaar
                    dictionary[year][i+1][0] = {} # key 0 voor de somatie over de maand
                    for j in range(31):
                        dictionary[year][i+1][j+1] = []  # voor iedere dag van de maand creer daglijst
                dictionary[year][month][day] = [element]  # nu alles gemaakt is kan element hier ook in
            dictionary[year][month][0][soort] = dictionary[year][month][0].get(soort, 0) + uitgave  # steek het bedrag van de entry in de lijst van soort entry onder de som key 0 (sommen over maand)
            dictionary[year][0][soort] = dictionary[year][0].get(soort, 0) + uitgave  # entry in somkey voor sommen over jaar (per soort)
            dictionary[0][soort] = dictionary[0].get(soort, 0) + uitgave  # entry in somkey voor sommen over altijd (per soort)
        return dictionary

    def report(self):

        def detailscalc(totaldict, hoodfdict):
            typelist = []  # list met de totale som per soort van opgegeven diction van tijdsduur
            total = 0  #netto over in het tijdsbereik
            for element in ['I', 'L', 'N', 'B', 'U', 'A', 'R', 'C', 'S']:  # voor iedere soort entry in de 0 diction
                if element in hoodfdict.keys():
                    total += totaldict.get(element, 0)  # iedere bijdrage bijtellen
                    typelist.append(element + ': ' + str(round(totaldict.get(element, 0), 2)))  # voeg soort toe: en totaal bedrag van de soort uitgave
            total -= totaldict.get('S', 0)  # sparen telt niet als bijdrage, dus als er is terug aftrekken
            return (round(total, 2), typelist)

        diction = self.dictioncreate()
        reportlist = []
        totallist = []
        details = detailscalc(diction[0], diction[0])
        totallist.append('Total: {} ->'.format(details[0]))
        for item in details[1]:
            totallist.append(item)
        reportlist.append(totallist)
        for year in sorted(diction.keys(), reverse=True):  # voor ieder jaar in dictionar
            reportlist.append([' - '])
            if year != 0:  # niet de somkey
                yearlist = []
                details = detailscalc(diction[year][0], diction[year][0])
                yearlist.append('Year {}: {} ->'.format(year, details[0]))
                for item in details[1]:
                    yearlist.append(item)
                reportlist.append(yearlist)
                reportlist.append([''])
                for month in diction[year].keys():  # voor iedere maand
                    if month != 0:  # niet de somkey
                        monthlist = []
                        details = detailscalc(diction[year][month][0], diction[year][0])
                        monthlist.append('{}/{}: {} ->'.format(month, year, details[0]))
                        for item in details[1]:
                            monthlist.append(item)
                        reportlist.append(monthlist)
        return reportlist

    def __init__(self, log, titlelist):
        QWidget.__init__(self)
        self.setWindowTitle('report')
        self.log = log
        self.titlelist = titlelist
        self.reportlist = self.report()

        # make fields and layouts
        self.mainlayout = QGridLayout()
        self.titlewidget = QWidget()
        self.titlelayout = QGridLayout()
        self.scroll = QScrollArea()
        self.reportwidget = QWidget()
        self.reportlayout = QGridLayout()

        # title field
        for i in range(len(self.titlelist)):
            for j in range(len(self.titlelist[i])):
                self.titlelayout.addWidget(QLabel(self.titlelist[i][j]), i,j)
        self.titlewidget.setLayout(self.titlelayout)

        # reportwidget
        maxlen = len(self.reportlist[0])
        for i in range(len(self.reportlist)):
            for j in range(len(self.reportlist[i])):
                if self.reportlist[i][j] == ' - ':
                    line = QFrame()
                    line.setFrameShape( QFrame.HLine )
                    line.setFrameShadow( QFrame.Raised )
                    self.reportlayout.addWidget(line, i,j,1,maxlen)
                else:
                    self.reportlayout.addWidget(QLabel(self.reportlist[i][j]), i,j)
        self.reportwidget.setLayout(self.reportlayout)

        #Scroll Area Properties
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.reportwidget)

        # main fields
        self.mainlayout.addWidget(self.titlewidget)
        self.mainlayout.addWidget(self.scroll)
        self.setLayout(self.mainlayout)

class Searcher(QWidget):
    def listcreate(self):
        lijst = []
        prelijst = self.values.log.split("\n")
        for item in prelijst:
            if item != '':
                lijst.append(item.split("\t"))
        return lijst

    def search_engine(self):
        list = []
        try:
            for element in self.list:
                include = True
                date = datetime.strptime(element[1], '%d/%m/%y')

                if self.mindate.text():
                    try:
                        mindate = datetime.strptime(self.mindate.text(), '%d/%m/%Y')
                    except:
                        mindate = datetime.strptime(self.mindate.text(), '%d/%m/%y')
                    if date < mindate:
                        include = False

                if self.maxdate.text():
                    try:
                        maxdate = datetime.strptime(self.maxdate.text(), '%d/%m/%Y')
                    except:
                        maxdate = datetime.strptime(self.maxdate.text(), '%d/%m/%y')
                    if date > maxdate:
                        include = False

                if self.minbedrag.text():
                    minbedrag = float(self.minbedrag.text())
                    if abs(float(element[3])) < minbedrag:
                        include = False

                if self.maxbedrag.text():
                    maxbedrag = float(self.maxbedrag.text())
                    if abs(float(element[3])) > maxbedrag:
                        include = False

                if self.type.text():
                    type = self.type.text().split(' & ')
                    if not any([type[i] in element[2] for i in range(len(type))]):
                        include = False

                if self.strings.text():
                    strings = self.strings.text().split(' & ')
                    if not any([strings[i].lower() in element[4].lower() for i in range(len(strings))]):
                        include = False

                if include:
                    list.append('\t'.join(element))
        except:
                self.msg = Dialog('Foutieve invoer', 'warning')
                self.msg.show()
        self.resultbox.setText('\n'.join(list))

    def reportclick(self):
        zoektermlist = []
        if self.mindate.text():
            try:
                mindate = datetime.strptime(self.mindate.text(), '%d/%m/%Y')
            except:
                mindate = datetime.strptime(self.mindate.text(), '%d/%m/%y')
            zoektermlist.append('-d:{}'.format(mindate))

        if self.maxdate.text():
            try:
                maxdate = datetime.strptime(self.maxdate.text(), '%d/%m/%Y')
            except:
                maxdate = datetime.strptime(self.maxdate.text(), '%d/%m/%y')
            zoektermlist.append('+d:{}'.format(maxdate))

        if self.minbedrag.text():
            minbedrag = float(self.minbedrag.text())
            zoektermlist.append('-b:{}'.format(minbedrag))

        if self.maxbedrag.text():
            maxbedrag = float(self.maxbedrag.text())
            zoektermlist.append('+b:{}'.format(maxbedrag))

        if self.type.text():
            zoektermlist.append('t:{}'.format(self.type.text()))

        if self.strings.text():
            zoektermlist.append('z:{}'.format(self.strings.text()))

        titlelist = [['Deelraport'], ['zoektermen:'], zoektermlist]
        self.report = Report(self.resultbox.toPlainText(), titlelist)
        self.report.show()

    def editclick(self):
        searchlist = self.resultbox.toPlainText().split('\n')
        loglist = self.values.log.split('\n')
        for line in searchlist:
            linelist = line.split('\t')
            loglist[int(linelist[0])] = line
        log = '\n'.join(loglist)
        self.values.log = log
        self.values.save()
        self.list = self.listcreate()
        self.msg = Dialog('Log bewerkt', 'info')
        self.msg.show()

    def __init__(self, values):
        QWidget.__init__(self)
        self.setWindowTitle('Search')
        self.values = values
        self.list = self.listcreate()


        self.mindate = QLineEdit()
        self.maxdate = QLineEdit()
        self.type = QLineEdit()
        self.minbedrag = QLineEdit()
        self.maxbedrag = QLineEdit()
        self.strings = QLineEdit()
        self.but = QPushButton('Search')
        self.resultbox = QTextEdit()
        self.reportbut = QPushButton('Deelraport')
        self.editbut = QPushButton('Bewerk log')

        self.but.clicked.connect(self.search_engine)
        self.reportbut.clicked.connect(self.reportclick)
        self.editbut.clicked.connect(self.editclick)

        self.layout = QGridLayout()
        self.layout.addWidget(QLabel('begin datum'), 0,0)
        self.layout.addWidget(QLabel('eind datum'), 1,0)
        self.layout.addWidget(self.mindate, 0,1)
        self.layout.addWidget(self.maxdate, 1,1)
        self.layout.addWidget(QLabel('minmum bedrag'), 0,2)
        self.layout.addWidget(QLabel('maximum bedrag'), 1,2)
        self.layout.addWidget(self.minbedrag, 0,3)
        self.layout.addWidget(self.maxbedrag, 1,3)
        self.layout.addWidget(QLabel('zoekterm'), 0,4)
        self.layout.addWidget(QLabel('type'), 1,4)
        self.layout.addWidget(self.strings, 0,5,1,2)
        self.layout.addWidget(self.type, 1,5)
        self.layout.addWidget(self.but, 1,6)
        self.layout.addWidget(self.resultbox, 2,0,7,7)
        self.layout.addWidget(self.reportbut, 9,0,1,3)
        self.layout.addWidget(self.editbut, 9,4,1,3)
        self.setLayout(self.layout)

app = QApplication([])
mainpage = Main()
mainpage.show()
sys.exit(app.exec())
