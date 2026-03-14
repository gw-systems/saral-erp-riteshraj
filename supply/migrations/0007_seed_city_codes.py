from django.db import migrations


def seed_city_codes(apps, schema_editor):
    """Seed CityCode with major Indian cities.
    Uses ON CONFLICT DO NOTHING to safely skip any existing records."""

    cities = [
        # (city_code, city_name, state_code)
        # Andhra Pradesh (AP)
        ('VIJ', 'Vijayawada', 'AP'),
        ('VIS', 'Visakhapatnam', 'AP'),
        ('GUN', 'Guntur', 'AP'),
        ('NLR', 'Nellore', 'AP'),
        ('KUR', 'Kurnool', 'AP'),
        ('KDP', 'Kadapa', 'AP'),
        ('TRP', 'Tirupati', 'AP'),
        ('RJM', 'Rajahmundry', 'AP'),
        # Assam (AS)
        ('GUW', 'Guwahati', 'AS'),
        ('SIL', 'Silchar', 'AS'),
        ('DIB', 'Dibrugarh', 'AS'),
        ('JOR', 'Jorhat', 'AS'),
        # Bihar (BR)
        ('PAT', 'Patna', 'BR'),
        ('GAY', 'Gaya', 'BR'),
        ('BHG', 'Bhagalpur', 'BR'),
        ('MUZ', 'Muzaffarpur', 'BR'),
        # Chhattisgarh (CG)
        ('RAI', 'Raipur', 'CG'),
        ('BLC', 'Bilaspur', 'CG'),
        ('DUG', 'Durg', 'CG'),
        ('KRB', 'Korba', 'CG'),
        # Goa (GA)
        ('PAN', 'Panaji', 'GA'),
        ('MRG', 'Margao', 'GA'),
        ('VDA', 'Vasco da Gama', 'GA'),
        # Gujarat (GJ)
        ('AMD', 'Ahmedabad', 'GJ'),
        ('SUR', 'Surat', 'GJ'),
        ('VAD', 'Vadodara', 'GJ'),
        ('RJK', 'Rajkot', 'GJ'),
        ('BHV', 'Bhavnagar', 'GJ'),
        ('JMN', 'Jamnagar', 'GJ'),
        ('GAN', 'Gandhinagar', 'GJ'),
        ('ANK', 'Ankleshwar', 'GJ'),
        ('VPI', 'Vapi', 'GJ'),
        # Haryana (HR)
        ('GRG', 'Gurugram', 'HR'),
        ('FAR', 'Faridabad', 'HR'),
        ('AMB', 'Ambala', 'HR'),
        ('HIS', 'Hisar', 'HR'),
        ('ROH', 'Rohtak', 'HR'),
        ('KRN', 'Karnal', 'HR'),
        ('PNP', 'Panipat', 'HR'),
        ('SNP', 'Sonipat', 'HR'),
        ('YNR', 'Yamunanagar', 'HR'),
        ('BAH', 'Bahadurgarh', 'HR'),
        # Himachal Pradesh (HP)
        ('SHI', 'Shimla', 'HP'),
        ('DHR', 'Dharamshala', 'HP'),
        ('MNL', 'Manali', 'HP'),
        # Jharkhand (JH)
        ('RAN', 'Ranchi', 'JH'),
        ('JMS', 'Jamshedpur', 'JH'),
        ('DHN', 'Dhanbad', 'JH'),
        ('BOK', 'Bokaro Steel City', 'JH'),
        # Karnataka (KA)
        ('BNG', 'Bengaluru', 'KA'),
        ('MYS', 'Mysuru', 'KA'),
        ('HUB', 'Hubballi', 'KA'),
        ('MNG', 'Mangaluru', 'KA'),
        ('BLG', 'Belagavi', 'KA'),
        ('GLP', 'Gulbarga', 'KA'),
        ('DVG', 'Davanagere', 'KA'),
        ('SHV', 'Shivamogga', 'KA'),
        ('TUM', 'Tumakuru', 'KA'),
        ('UDU', 'Udupi', 'KA'),
        # Kerala (KL)
        ('TRV', 'Thiruvananthapuram', 'KL'),
        ('COC', 'Kochi', 'KL'),
        ('KOZ', 'Kozhikode', 'KL'),
        ('THR', 'Thrissur', 'KL'),
        ('KLL', 'Kollam', 'KL'),
        ('ALP', 'Alappuzha', 'KL'),
        # Madhya Pradesh (MP)
        ('BPL', 'Bhopal', 'MP'),
        ('IND', 'Indore', 'MP'),
        ('GWL', 'Gwalior', 'MP'),
        ('JAB', 'Jabalpur', 'MP'),
        ('UJJ', 'Ujjain', 'MP'),
        ('SAG', 'Sagar', 'MP'),
        ('REW', 'Rewa', 'MP'),
        ('SNG', 'Singrauli', 'MP'),
        ('PIT', 'Pithampur', 'MP'),
        ('DEW', 'Dewas', 'MP'),
        # Maharashtra (MH)
        ('MUM', 'Mumbai', 'MH'),
        ('PUN', 'Pune', 'MH'),
        ('NAG', 'Nagpur', 'MH'),
        ('THA', 'Thane', 'MH'),
        ('NSK', 'Nashik', 'MH'),
        ('AGA', 'Aurangabad', 'MH'),
        ('SOL', 'Solapur', 'MH'),
        ('KLH', 'Kolhapur', 'MH'),
        ('AMV', 'Amravati', 'MH'),
        ('NVM', 'Navi Mumbai', 'MH'),
        ('PLG', 'Palghar', 'MH'),
        ('RTG', 'Ratnagiri', 'MH'),
        ('SAT', 'Satara', 'MH'),
        ('SGL', 'Sangli', 'MH'),
        ('JLG', 'Jalgaon', 'MH'),
        ('AKL', 'Akola', 'MH'),
        ('CHD', 'Chandrapur', 'MH'),
        ('YAV', 'Yavatmal', 'MH'),
        ('LAT', 'Latur', 'MH'),
        ('NND', 'Nanded', 'MH'),
        ('BHW', 'Bhusawal', 'MH'),
        ('PNV', 'Panvel', 'MH'),
        ('KLN', 'Kalyan', 'MH'),
        ('DMB', 'Dombivli', 'MH'),
        ('ULS', 'Ulhasnagar', 'MH'),
        ('VSI', 'Vasai', 'MH'),
        ('WSH', 'Washim', 'MH'),
        ('RGD', 'Raigad', 'MH'),
        ('WRD', 'Wardha', 'MH'),
        ('BDH', 'Buldhana', 'MH'),
        ('GON', 'Gondia', 'MH'),
        ('GDC', 'Gadchiroli', 'MH'),
        ('BHN', 'Bhandara', 'MH'),
        ('ALB', 'Alibag', 'MH'),
        ('OSM', 'Osmanabad', 'MH'),
        ('HNG', 'Hingoli', 'MH'),
        ('PRB', 'Parbhani', 'MH'),
        ('BED', 'Beed', 'MH'),
        ('AHN', 'Ahmednagar', 'MH'),
        ('DHU', 'Dhule', 'MH'),
        ('NDB', 'Nandurbar', 'MH'),
        # Odisha (OD)
        ('BHB', 'Bhubaneswar', 'OD'),
        ('CUT', 'Cuttack', 'OD'),
        ('ROK', 'Rourkela', 'OD'),
        ('SAM', 'Sambalpur', 'OD'),
        ('BER', 'Berhampur', 'OD'),
        # Punjab (PB)
        ('LDH', 'Ludhiana', 'PB'),
        ('AMR', 'Amritsar', 'PB'),
        ('JAL', 'Jalandhar', 'PB'),
        ('PTL', 'Patiala', 'PB'),
        ('BTH', 'Bathinda', 'PB'),
        ('MHL', 'Mohali', 'PB'),
        # Rajasthan (RJ)
        ('JAI', 'Jaipur', 'RJ'),
        ('JOD', 'Jodhpur', 'RJ'),
        ('UDA', 'Udaipur', 'RJ'),
        ('KOT', 'Kota', 'RJ'),
        ('AJM', 'Ajmer', 'RJ'),
        ('BIK', 'Bikaner', 'RJ'),
        ('BHP', 'Bharatpur', 'RJ'),
        ('ALW', 'Alwar', 'RJ'),
        ('SIK', 'Sikar', 'RJ'),
        # Tamil Nadu (TN)
        ('CHE', 'Chennai', 'TN'),
        ('COI', 'Coimbatore', 'TN'),
        ('MAD', 'Madurai', 'TN'),
        ('TRR', 'Tiruchirappalli', 'TN'),
        ('SAL', 'Salem', 'TN'),
        ('TNV', 'Tirunelveli', 'TN'),
        ('ERO', 'Erode', 'TN'),
        ('VEL', 'Vellore', 'TN'),
        ('TUP', 'Thoothukudi', 'TN'),
        ('DIN', 'Dindigul', 'TN'),
        ('KAN', 'Kanchipuram', 'TN'),
        # Telangana (TS)
        ('HYD', 'Hyderabad', 'TS'),
        ('WAR', 'Warangal', 'TS'),
        ('NZB', 'Nizamabad', 'TS'),
        ('KRM', 'Karimnagar', 'TS'),
        ('KHA', 'Khammam', 'TS'),
        ('SEC', 'Secunderabad', 'TS'),
        # Uttar Pradesh (UP)
        ('LKN', 'Lucknow', 'UP'),
        ('KNP', 'Kanpur', 'UP'),
        ('AGR', 'Agra', 'UP'),
        ('VNS', 'Varanasi', 'UP'),
        ('MRT', 'Meerut', 'UP'),
        ('PRY', 'Prayagraj', 'UP'),
        ('GZB', 'Ghaziabad', 'UP'),
        ('NOI', 'Noida', 'UP'),
        ('GOR', 'Gorakhpur', 'UP'),
        ('MAT', 'Mathura', 'UP'),
        ('ALG', 'Aligarh', 'UP'),
        ('BAL', 'Bareilly', 'UP'),
        ('SAH', 'Saharanpur', 'UP'),
        ('MOR', 'Moradabad', 'UP'),
        ('FAZ', 'Faizabad', 'UP'),
        ('JNP', 'Jaunpur', 'UP'),
        ('GNO', 'Greater Noida', 'UP'),
        ('FZB', 'Firozabad', 'UP'),
        ('SHJ', 'Shahjahanpur', 'UP'),
        # Uttarakhand (UK)
        ('DDN', 'Dehradun', 'UK'),
        ('HDW', 'Haridwar', 'UK'),
        ('HLD', 'Haldwani', 'UK'),
        ('ROR', 'Roorkee', 'UK'),
        # West Bengal (WB)
        ('KOL', 'Kolkata', 'WB'),
        ('HWR', 'Howrah', 'WB'),
        ('DPR', 'Durgapur', 'WB'),
        ('ASN', 'Asansol', 'WB'),
        ('SBR', 'Siliguri', 'WB'),
        ('BRD', 'Bardhaman', 'WB'),
        # Delhi (DL)
        ('DEL', 'New Delhi', 'DL'),
        ('DLI', 'Delhi', 'DL'),
        # Jammu & Kashmir (JK)
        ('SRN', 'Srinagar', 'JK'),
        ('JMU', 'Jammu', 'JK'),
        # Chandigarh (CH)
        ('CHA', 'Chandigarh', 'CH'),
        # Puducherry (PY)
        ('PON', 'Puducherry', 'PY'),
    ]

    # Use raw SQL INSERT ... ON CONFLICT DO NOTHING to safely skip any
    # existing records without raising IntegrityError
    with schema_editor.connection.cursor() as cursor:
        for code, name, state_code in cities:
            cursor.execute(
                """
                INSERT INTO city_codes (city_code, city_name, state_code, is_active,
                                        created_at, updated_at)
                VALUES (%s, %s, %s, TRUE, NOW(), NOW())
                ON CONFLICT DO NOTHING
                """,
                [code, name, state_code]
            )


def reverse_seed(apps, schema_editor):
    # Only remove records we added (identified by city_code)
    codes = [
        'VIJ', 'VIS', 'GUN', 'NLR', 'KUR', 'KDP', 'TRP', 'RJM',
        'GUW', 'SIL', 'DIB', 'JOR',
        'PAT', 'GAY', 'BHG', 'MUZ',
        'RAI', 'BLC', 'DUG', 'KRB',
        'PAN', 'MRG', 'VDA',
        'AMD', 'SUR', 'VAD', 'RJK', 'BHV', 'JMN', 'GAN', 'ANK', 'VPI',
        'GRG', 'FAR', 'AMB', 'HIS', 'ROH', 'KRN', 'PNP', 'SNP', 'YNR', 'BAH',
        'SHI', 'DHR', 'MNL',
        'RAN', 'JMS', 'DHN', 'BOK',
        'BNG', 'MYS', 'HUB', 'MNG', 'BLG', 'GLP', 'DVG', 'SHV', 'TUM', 'UDU',
        'TRV', 'COC', 'KOZ', 'THR', 'KLL', 'ALP',
        'BPL', 'IND', 'GWL', 'JAB', 'UJJ', 'SAG', 'REW', 'SNG', 'PIT', 'DEW',
        'MUM', 'PUN', 'NAG', 'THA', 'NSK', 'AGA', 'SOL', 'KLH', 'AMV', 'NVM',
        'PLG', 'RTG', 'SAT', 'SGL', 'JLG', 'AKL', 'CHD', 'YAV', 'LAT', 'NND',
        'BHW', 'PNV', 'KLN', 'DMB', 'ULS', 'VSI', 'WSH', 'RGD', 'WRD', 'BDH',
        'GON', 'GDC', 'BHN', 'ALB', 'OSM', 'HNG', 'PRB', 'BED', 'AHN', 'DHU', 'NDB',
        'BHB', 'CUT', 'ROK', 'SAM', 'BER',
        'LDH', 'AMR', 'JAL', 'PTL', 'BTH', 'MHL',
        'JAI', 'JOD', 'UDA', 'KOT', 'AJM', 'BIK', 'BHP', 'ALW', 'SIK',
        'CHE', 'COI', 'MAD', 'TRR', 'SAL', 'TNV', 'ERO', 'VEL', 'TUP', 'DIN', 'KAN',
        'HYD', 'WAR', 'NZB', 'KRM', 'KHA', 'SEC',
        'LKN', 'KNP', 'AGR', 'VNS', 'MRT', 'PRY', 'GZB', 'NOI', 'GOR', 'MAT',
        'ALG', 'BAL', 'SAH', 'MOR', 'FAZ', 'JNP', 'GNO', 'FZB', 'SHJ',
        'DDN', 'HDW', 'HLD', 'ROR',
        'KOL', 'HWR', 'DPR', 'ASN', 'SBR', 'BRD',
        'DEL', 'DLI',
        'SRN', 'JMU',
        'CHA',
        'PON',
    ]
    with schema_editor.connection.cursor() as cursor:
        placeholders = ','.join(['%s'] * len(codes))
        cursor.execute(
            f"DELETE FROM city_codes WHERE city_code IN ({placeholders})",
            codes
        )


class Migration(migrations.Migration):

    dependencies = [
        ('supply', '0006_alter_rfqvendormapping_gmail_email'),
        ('dropdown_master_data', '0016_seed_regions_states'),
    ]

    operations = [
        migrations.RunPython(seed_city_codes, reverse_seed),
    ]
