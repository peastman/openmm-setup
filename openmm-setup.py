import simtk.openmm.app as app
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
import datetime

app = Flask(__name__)
app.config.from_object(__name__)
app.config.update({'SECRET_KEY':'development key'})

@app.route('/')
def showSelectFileType():
    return render_template('selectFileType.html')

@app.route('/selectFiles')
def selectFiles():
    session['fileType'] = request.args.get('type', '')
    return showConfigureFiles()

def showConfigureFiles():
    try:
        fileType = session['fileType']
        if fileType in ('pdb', 'pdbx'):
            return render_template('configurePdbFile.html')
    except:
        app.logger.error('Error displaying configure files page', exc_info=True)
    # The file type is invalid, so send them back to the select file type page.
    return showSelectFileType()

@app.route('/configureFiles')
def configureFiles():
    fileType = session['fileType']
    if fileType in ('pdb', 'pdbx'):
        session['filename'] = request.args.get('filename', '')
        session['forcefield'] = request.args.get('forcefield', '')
        session['waterModel'] = request.args.get('waterModel', '')
        configureDefaultOptions()
        return showSimulationOptions()

def showSimulationOptions():
    return render_template('simulationOptions.html', title='Simulation Options')

@app.route('/setSimulationOptions', methods=['POST'])
def setSimulationOptions():
    for key in request.form:
        session[key] = request.form[key]
    session['writeDCD'] = 'writeDCD' in request.form
    session['writeData'] = 'writeData' in request.form
    session['dataFields'] = request.form.getlist('dataFields')
    return createScript()

def configureDefaultOptions():
    """Select default options based on the file format and force field."""
    session['ensemble'] = 'npt'
    session['platform'] = 'CUDA'
    session['precision'] = 'single'
    session['cutoff'] = '1.0'
    session['ewaldTol'] = '0.0005'
    session['constraintTol'] = '0.000001'
    session['dt'] = '0.002'
    session['steps'] = '1000000'
    session['equilibrationSteps'] = '1000'
    session['temperature'] = '300'
    session['friction'] = '1.0'
    session['pressure'] = '1.0'
    session['barostatInterval'] = '25'
    session['nonbondedMethod'] = 'PME'
    session['writeDCD'] = True
    session['dcdFilename'] = 'trajectory.dcd'
    session['dcdInterval'] = '10000'
    session['writeData'] = True
    session['dataFilename'] = 'log.txt'
    session['dataInterval'] = '1000'
    session['dataFields'] = ['step', 'speed' ,'progress', 'potentialEnergy', 'temperature']
    isAmoeba = session['fileType'] in ('pdb', 'pdbx') and 'amoeba' in session['forcefield']
    if isAmoeba:
        session['constraints'] = 'none'
    else:
        session['constraints'] = 'hbonds'

def createScript():
    script = []
    
    # Header
    
    script.append('# This script was generated by OpenMM-Setup on %s.\n' % datetime.date.today())
    script.append('from simtk.openmm import *')
    script.append('from simtk.openmm.app import *')
    script.append('from simtk.unit import *')
    
    # Input files
    
    script.append('\n# Input Files\n')
    if session['fileType'] == 'pdb':
        script.append("pdb = PDBFile('%s')" % session['filename'])
    elif session['fileType'] == 'pdbx':
        script.append("pdbx = PDBxFile('%s')" % session['filename'])
    if session['fileType'] in ('pdb', 'pdbx'):
        forcefield = session['forcefield']
        water = session['waterModel']
        if water == 'implicit':
            models = {'amber99sb.xml': 'amber99_obc.xml',
                      'amber99sbildn.xml': 'amber99_obc.xml',
                      'amber03.xml': 'amber03_obc.xml',
                      'amber10.xml': 'amber10_obc.xml',
                      'amoeba2013.xml': 'amoeba2013_gk.xml'}
            water = models[forcefield]
        script.append("forcefield = ForceField('%s', '%s')" % (forcefield, water))

    # System configuration

    script.append('\n# System Configuration\n')
    nonbondedMethod = session['nonbondedMethod']
    script.append('nonbondedMethod = %s' % nonbondedMethod)
    if nonbondedMethod != 'NoCutoff':
        script.append('nonbondedCutoff = %s*nanometers' % session['cutoff'])
    if nonbondedMethod == 'PME':
        script.append('ewaldErrorTolerance = %s' % session['ewaldTol'])
    constraints = session['constraints']
    constraintMethods = {'none': 'None',
                         'water': 'None',
                         'hbonds': 'HBonds',
                         'allbonds': 'AllBonds'}
    script.append('constraints = %s' % constraintMethods[constraints])
    script.append('rigidWater = %s' % ('False' if constraints == 'none' else 'True'))
    if constraints != 'none':
        script.append('constraintTolerance = %s' % session['constraintTol'])

    # Integration options

    script.append('\n# Integration Options\n')
    script.append('dt = %s*picoseconds' % session['dt'])
    ensemble = session['ensemble']
    if ensemble in ('nvt', 'npt'):
        script.append('temperature = %s*kelvin' % session['temperature'])
        script.append('friction = %s/picosecond' % session['friction'])
    if ensemble == 'npt':
        script.append('pressure = %s*atmospheres' % session['pressure'])
        script.append('barostatInterval = %s' % session['barostatInterval'])

    # Simulation options

    script.append('\n# Simulation Options\n')
    script.append('steps = %s' % session['steps'])
    script.append('equilibrationSteps = %s' % session['equilibrationSteps'])
    script.append('platform = %s' % session['platform'])
    if session['platform'] in ('CUDA', 'OpenCL'):
        script.append("platformProperties = {'Precision': '%s'}" % session['precision'])
    if session['writeDCD']:
        script.append("dcdReporter = DCDReporter('%s', %s)" % (session['dcdFilename'], session['dcdInterval']))
    if session['writeData']:
        args = ', '.join('%s=True' % field for field in session['dataFields'])
        script.append("dataReporter = StateDataReporter('%s', %s," % (session['dataFilename'], session['dataInterval']))
        script.append("    %s, separator='\\t', totalSteps=%s)" % (args, session['steps']))
    
    # Prepare the simulation
    
    script.append('\n# Prepare the Simulation\n')
    script.append("print('Building system...')")
    if session['fileType'] == 'pdb':
        script.append('topology = pdb.topology')
        script.append('positions = pdb.positions')
    elif session['fileType'] == 'pdbx':
        script.append('topology = pdbx.topology')
        script.append('positions = pdbx.positions')
    script.append('system = forcefield.createSystem(topology, nonbondedMethod=nonbondedMethod,%s' % (' nonbondedCutoff=nonbondedCutoff,' if nonbondedMethod != 'NoCutoff' else ''))
    script.append('    constraints=constraints, rigidWater=rigidWater%s)' % (', ewaldErrorTolerance=ewaldErrorTolerance' if nonbondedMethod == 'PME' else ''))
    if ensemble == 'npt':
        script.append('system.addForce(MonteCarloBarostat(pressure, temperature, barostatInterval))')
    if ensemble == 'nve':
        script.append('integrator = VerletIntegrator(dt)')
    else:
        script.append('integrator = LangevinIntegrator(temperature, friction, dt)')
    if constraints != 'none':
        script.append('integrator.setConstraintTolerance(constraintTolerance)')
    script.append('simulation = Simulation(topology, system, integrator, platform%s)' % (', platformProperties' if session['platform'] in ('CUDA', 'OpenCL') else ''))
    script.append('simulation.context.setPositions(positions)')
    
    # Minimize and equilibrate
    
    script.append('\n# Minimize and Equilibrate\n')
    script.append("print('Performing energy minimization...')")
    script.append('simulation.minimizeEnergy()')
    script.append("print('Equilibrating...')")
    script.append('simulation.context.setVelocitiesToTemperature(temperature)')
    script.append('simulation.step(equilibrationSteps)')
    
    # Simulate
    
    script.append('\n# Simulate\n')
    script.append("print('Simulating...')")
    if session['writeDCD']:
        script.append('simulation.reporters.append(dcdReporter)')
    if session['writeData']:
        script.append('simulation.reporters.append(dataReporter)')
    script.append('simulation.currentStep = 0')
    script.append('simulation.step(steps)')

    return "\n".join(script)